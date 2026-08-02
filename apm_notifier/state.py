from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from .models import Job, SourceResult, utc_now


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    fingerprint TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    location TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    notified_at TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    last_checked_at TEXT NOT NULL,
    last_success_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    last_match_count INTEGER NOT NULL DEFAULT 0,
    health_alerted_at TEXT
);
"""


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def is_initialized(self) -> bool:
        row = self.connection.execute("SELECT value FROM meta WHERE key = 'initialized'").fetchone()
        return bool(row and row["value"] == "true")

    def mark_initialized(self) -> None:
        self.connection.execute(
            "INSERT INTO meta(key, value) VALUES('initialized', 'true') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        self.connection.commit()

    def record_jobs(self, jobs: tuple[Job, ...]) -> None:
        checked_at = utc_now()
        with self.connection:
            for job in jobs:
                self.connection.execute(
                    """
                    INSERT INTO jobs(
                        fingerprint, source_id, company, title, url, location,
                        first_seen_at, last_seen_at, notified_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(fingerprint) DO UPDATE SET
                        last_seen_at = excluded.last_seen_at,
                        location = excluded.location
                    """,
                    (
                        job.fingerprint,
                        job.source_id,
                        job.company,
                        job.title,
                        job.url,
                        job.location,
                        checked_at,
                        checked_at,
                    ),
                )

    def pending_jobs(self) -> tuple[Job, ...]:
        rows = self.connection.execute(
            """
            SELECT source_id, company, title, url, location, first_seen_at
            FROM jobs WHERE notified_at IS NULL ORDER BY first_seen_at, company, title
            """
        ).fetchall()
        return tuple(
            Job(
                source_id=row["source_id"],
                company=row["company"],
                title=row["title"],
                url=row["url"],
                location=row["location"],
                discovered_at=row["first_seen_at"],
            )
            for row in rows
        )

    def mark_notified(self, job: Job) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET notified_at = ? WHERE fingerprint = ?",
                (utc_now(), job.fingerprint),
            )

    def silence_pending(self) -> None:
        with self.connection:
            self.connection.execute(
                "UPDATE jobs SET notified_at = ? WHERE notified_at IS NULL",
                (utc_now(),),
            )

    def record_source_result(self, result: SourceResult) -> bool:
        """Persist health and return True when a throttled health alert is due."""
        now = utc_now()
        previous = self.connection.execute(
            "SELECT consecutive_failures, health_alerted_at FROM source_health WHERE source_id = ?",
            (result.source.id,),
        ).fetchone()
        prior_failures = int(previous["consecutive_failures"]) if previous else 0
        previous_alert = previous["health_alerted_at"] if previous else None

        if result.succeeded:
            failures = 0
            last_success = now
            last_error = "; ".join(result.errors)[:1000]
        else:
            failures = prior_failures + 1
            last_success = None
            last_error = "; ".join(result.errors)[:1000] or "unknown source failure"

        should_alert = not result.succeeded and failures >= 3 and self._alert_is_due(previous_alert)
        alerted_at = now if should_alert else previous_alert
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO source_health(
                    source_id, source_name, last_checked_at, last_success_at,
                    consecutive_failures, last_error, last_match_count, health_alerted_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = COALESCE(excluded.last_success_at, source_health.last_success_at),
                    consecutive_failures = excluded.consecutive_failures,
                    last_error = excluded.last_error,
                    last_match_count = excluded.last_match_count,
                    health_alerted_at = excluded.health_alerted_at
                """,
                (
                    result.source.id,
                    result.source.name,
                    now,
                    last_success,
                    failures,
                    last_error,
                    len(result.jobs),
                    alerted_at,
                ),
            )
        return should_alert

    @staticmethod
    def _alert_is_due(previous_alert: str | None) -> bool:
        if not previous_alert:
            return True
        then = datetime.fromisoformat(previous_alert)
        return datetime.now(timezone.utc) - then >= timedelta(hours=24)

    def status_rows(self) -> tuple[sqlite3.Row, ...]:
        return tuple(
            self.connection.execute(
                """
                SELECT source_name, last_checked_at, last_success_at,
                       consecutive_failures, last_match_count, last_error
                FROM source_health
                ORDER BY consecutive_failures DESC, source_name
                """
            ).fetchall()
        )

    def job_counts(self) -> tuple[int, int]:
        row = self.connection.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN notified_at IS NULL THEN 1 ELSE 0 END) AS pending FROM jobs"
        ).fetchone()
        return int(row["total"] or 0), int(row["pending"] or 0)
