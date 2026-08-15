from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from apm_notifier.models import Job, Source, SourceResult
from apm_notifier.state import StateStore


class StateStoreTests(unittest.TestCase):
    def test_deduplicates_and_preserves_pending_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            try:
                job = Job(
                    source_id="example",
                    company="Example",
                    title="Product Manager Intern 2027",
                    url="https://example.com/jobs/1?utm_source=test",
                )
                duplicate = Job(
                    source_id="example",
                    company="Example",
                    title="Product Manager Intern 2027",
                    url="https://example.com/jobs/1",
                )
                store.record_jobs((job, duplicate))
                self.assertEqual(len(store.pending_jobs()), 1)
                store.mark_notified(job)
                self.assertEqual(store.pending_jobs(), ())
                store.record_jobs((duplicate,))
                self.assertEqual(store.pending_jobs(), ())
            finally:
                store.close()

    def test_health_alert_waits_for_six_hour_outage_and_resets_on_recovery(self) -> None:
        source = Source(
            id="example",
            name="Example",
            urls=("https://example.com/jobs",),
            career_url="https://example.com/careers",
        )
        failure = SourceResult(
            source=source,
            jobs=(),
            fetched_urls=0,
            errors=("HTTP Error 503: Service Temporarily Unavailable",),
        )
        success = SourceResult(source=source, jobs=(), fetched_urls=1)
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            try:
                with patch("apm_notifier.state.utc_now", return_value="2026-08-15T00:00:00+00:00"):
                    self.assertFalse(store.record_source_result(failure))
                with patch("apm_notifier.state.utc_now", return_value="2026-08-15T05:59:00+00:00"):
                    self.assertFalse(store.record_source_result(failure))
                with patch("apm_notifier.state.utc_now", return_value="2026-08-15T06:00:00+00:00"):
                    self.assertTrue(store.record_source_result(failure))
                with patch("apm_notifier.state.utc_now", return_value="2026-08-16T06:00:00+00:00"):
                    self.assertFalse(store.record_source_result(failure))
                with patch("apm_notifier.state.utc_now", return_value="2026-08-16T07:00:00+00:00"):
                    self.assertFalse(store.record_source_result(success))
                with patch("apm_notifier.state.utc_now", return_value="2026-08-16T08:00:00+00:00"):
                    self.assertFalse(store.record_source_result(failure))
            finally:
                store.close()

    def test_migrates_existing_source_health_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.sqlite3"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE source_health (
                    source_id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL,
                    last_success_at TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    last_match_count INTEGER NOT NULL DEFAULT 0,
                    health_alerted_at TEXT
                )
                """
            )
            connection.commit()
            connection.close()

            store = StateStore(path)
            try:
                columns = {
                    row["name"]
                    for row in store.connection.execute(
                        "PRAGMA table_info(source_health)"
                    ).fetchall()
                }
                self.assertIn("failure_started_at", columns)
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
