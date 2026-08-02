from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import logging
import time

from .extract import extract_jobs
from .fetch import BrowserRenderer, HttpClient
from .filtering import RoleFilter
from .models import Job, Source, SourceResult
from .notify import NotificationManager
from .state import StateStore


LOGGER = logging.getLogger("apm_notifier")


@dataclass(frozen=True)
class RunSummary:
    sources_ok: int
    sources_failed: int
    matches: int
    alerts_delivered: int
    alerts_pending: int


class Monitor:
    def __init__(
        self,
        sources: tuple[Source, ...],
        client: HttpClient,
        role_filter: RoleFilter,
        store: StateStore,
        notifier: NotificationManager,
        concurrency: int,
        alert_on_first_run: bool,
    ) -> None:
        self.sources = sources
        self.client = client
        self.role_filter = role_filter
        self.store = store
        self.notifier = notifier
        self.concurrency = concurrency
        self.alert_on_first_run = alert_on_first_run
        self.browser = BrowserRenderer(client.timeout_seconds)

    def run_once(self, dry_run: bool = False) -> RunSummary:
        LOGGER.info("Checking %d career sources", len(self.sources))
        results: list[SourceResult] = []
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            futures = {executor.submit(self._check_source, source): source for source in self.sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = SourceResult(source=source, jobs=(), fetched_urls=0, errors=(str(error),))
                results.append(result)
                level = logging.INFO if result.succeeded else logging.WARNING
                LOGGER.log(
                    level,
                    "%s: %d matching role(s), %d/%d page(s) fetched%s",
                    source.name,
                    len(result.jobs),
                    result.fetched_urls,
                    len(source.urls),
                    f"; {'; '.join(result.errors)}" if result.errors else "",
                )

        jobs_by_fingerprint: dict[str, Job] = {}
        for result in results:
            for job in result.jobs:
                jobs_by_fingerprint[job.fingerprint] = job
        jobs = tuple(jobs_by_fingerprint.values())

        succeeded = sum(result.succeeded for result in results)
        failed = len(results) - succeeded
        if dry_run:
            self._print_dry_run(jobs)
            return RunSummary(succeeded, failed, len(jobs), 0, len(jobs))

        first_run = not self.store.is_initialized()
        self.store.record_jobs(jobs)
        for result in results:
            if self.store.record_source_result(result):
                outcome = self.notifier.send_health(result)
                if outcome.errors:
                    LOGGER.error("Health alert failed: %s", "; ".join(outcome.errors))

        if first_run and not self.alert_on_first_run:
            self.store.silence_pending()
        if succeeded:
            self.store.mark_initialized()

        delivered = 0
        if self.notifier.configured_channels:
            for job in self.store.pending_jobs():
                outcome = self.notifier.send_job(job)
                if outcome.delivered:
                    self.store.mark_notified(job)
                    delivered += 1
                    LOGGER.info("Alert delivered: %s — %s", job.company, job.title)
                if outcome.errors:
                    LOGGER.error("Alert channel error for %s: %s", job.title, "; ".join(outcome.errors))
        else:
            LOGGER.warning(
                "No phone notification channel is configured; matching jobs remain pending. "
                "Set Telegram or ntfy values in .env."
            )

        pending = len(self.store.pending_jobs())
        LOGGER.info(
            "Check complete: %d source(s) OK, %d failed, %d match(es), %d alert(s) delivered, %d pending",
            succeeded,
            failed,
            len(jobs),
            delivered,
            pending,
        )
        return RunSummary(succeeded, failed, len(jobs), delivered, pending)

    def run_forever(self, interval_seconds: int) -> None:
        LOGGER.info("Starting monitor loop; checking every %d seconds", interval_seconds)
        while True:
            started = time.monotonic()
            try:
                self.run_once()
            except Exception:
                LOGGER.exception("Monitor cycle failed")
            elapsed = time.monotonic() - started
            time.sleep(max(1, interval_seconds - elapsed))

    def _check_source(self, source: Source) -> SourceResult:
        jobs: dict[str, Job] = {}
        errors: list[str] = []
        fetched = 0
        for url in source.urls:
            try:
                response = self.browser.fetch(url) if source.render else self.client.fetch(url, source.headers)
                fetched += 1
                for job in extract_jobs(
                    response.text,
                    response.content_type,
                    source,
                    response.final_url,
                    self.role_filter,
                ):
                    jobs[job.fingerprint] = job
            except Exception as error:
                errors.append(str(error))
        return SourceResult(
            source=source,
            jobs=tuple(jobs.values()),
            fetched_urls=fetched,
            errors=tuple(errors),
        )

    @staticmethod
    def _print_dry_run(jobs: tuple[Job, ...]) -> None:
        if not jobs:
            print("Dry run found no matching roles.")
            return
        print(f"Dry run found {len(jobs)} matching role(s):")
        for job in sorted(jobs, key=lambda item: (item.company, item.title)):
            location = f" — {job.location}" if job.location else ""
            print(f"- {job.company}: {job.title}{location}\n  {job.url}")
