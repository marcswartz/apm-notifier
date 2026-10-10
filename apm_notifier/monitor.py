from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from collections.abc import Iterator
import logging
import json
import re
import time

from .extract import CareerHTMLParser, LinkedInJobCardParser, extract_jobs, response_has_job_signal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .fetch import BrowserRenderer, HttpClient
from .filtering import RoleFilter
from .models import FetchResult, Job, Source, SourceResult
from .notify import NotificationManager
from .state import StateStore
from .tiktok import normalize_search_response


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
        baseline_only = not dry_run and not self.store.is_initialized() and not self.alert_on_first_run
        delivered = 0
        attempted_alerts: set[str] = set()
        with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
            sources = sorted(self.sources, key=lambda source: not source.priority)
            futures = {executor.submit(self._check_source, source): source for source in sources}
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
                if not dry_run:
                    if self.store.record_source_result(result):
                        outcome = self.notifier.send_health(result)
                        if outcome.errors:
                            LOGGER.error("Health alert failed: %s", "; ".join(outcome.errors))
                    if source.priority:
                        self.store.record_jobs(result.jobs)
                        if not baseline_only:
                            delivered += self._deliver_pending_jobs(attempted_alerts)

        jobs_by_role: dict[tuple[str, str], Job] = {}
        for result in results:
            for job in result.jobs:
                role_key = job.role_key
                current = jobs_by_role.get(role_key)
                if current is None or (
                    current.source_id.endswith("backcheck")
                    and not job.source_id.endswith("backcheck")
                ):
                    jobs_by_role[role_key] = job
        jobs = tuple(jobs_by_role.values())

        succeeded = sum(result.succeeded for result in results)
        failed = len(results) - succeeded
        if dry_run:
            self._print_dry_run(jobs)
            return RunSummary(succeeded, failed, len(jobs), 0, len(jobs))

        self.store.record_jobs(jobs)
        if baseline_only:
            self.store.silence_pending()
        if succeeded:
            self.store.mark_initialized()

        if self.notifier.configured_channels:
            delivered += self._deliver_pending_jobs(attempted_alerts)
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

    def _deliver_pending_jobs(self, attempted: set[str]) -> int:
        if not self.notifier.configured_channels:
            return 0
        delivered = 0
        for job in self.store.pending_jobs():
            if job.fingerprint in attempted:
                continue
            attempted.add(job.fingerprint)
            outcome = self.notifier.send_job(job)
            if outcome.delivered:
                self.store.mark_notified(job)
                delivered += 1
                LOGGER.info("Alert delivered: %s — %s", job.company, job.title)
            if outcome.errors:
                LOGGER.error("Alert channel error for %s: %s", job.title, "; ".join(outcome.errors))
        return delivered

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
        education_checks: dict[str, bool] = {}
        for index, url in enumerate(source.urls):
            try:
                for response in self._source_responses(source, index, url):
                    for job in extract_jobs(
                        response.text,
                        response.content_type,
                        source,
                        response.final_url,
                        self.role_filter,
                    ):
                        if source.verify_job_links and not self.client.url_exists(job.url):
                            LOGGER.warning("Skipping confirmed dead back-check link: %s", job.url)
                            continue
                        if (
                            source.verify_graduate_education
                            and self.role_filter.is_graduate_role(job.title)
                        ):
                            if job.fingerprint not in education_checks:
                                detail_text = job.requirements or self.client.fetch(job.url).text
                                education_checks[job.fingerprint] = self.role_filter.allows_bachelors(
                                    detail_text, title=job.title,
                                )
                            if not education_checks[job.fingerprint]:
                                LOGGER.info(
                                    "Skipping postgraduate-only role: %s — %s",
                                    source.name,
                                    job.title,
                                )
                                continue
                        jobs[job.fingerprint] = job
                fetched += 1
            except Exception as error:
                errors.append(str(error))
        return SourceResult(
            source=source,
            jobs=tuple(jobs.values()),
            fetched_urls=fetched,
            errors=tuple(errors),
        )

    def _source_responses(self, source: Source, index: int, url: str) -> Iterator[FetchResult]:
        body = source.request_bodies[index] if source.request_bodies else ""
        previous_pages: set[str] = set()
        total: int | None = None
        page_url = url
        for _ in range(50):
            if source.render:
                if source.request_method != "GET" or body or source.paginate:
                    raise ValueError("Rendered sources only support unpaginated GET requests")
                response = self.browser.fetch(url)
            else:
                response = self.client.fetch(
                    page_url, source.headers, method=source.request_method, body=body,
                )
            response = normalize_search_response(response)
            if source.paginate and "linkedin.com/jobs-guest/" in url:
                cards = LinkedInJobCardParser()
                cards.feed(response.text)
                if not cards.cards:
                    empty_fragment = re.sub(r"<!DOCTYPE html>|<!--.*?-->", "", response.text, flags=re.IGNORECASE | re.DOTALL)
                    if not empty_fragment.strip():
                        return
                    if not response_has_job_signal(response.text, response.content_type):
                        raise ValueError(f"{page_url}: LinkedIn returned an unreadable search page")
                    return
                page_key = json.dumps(cards.cards)
                if page_key in previous_pages:
                    raise ValueError(f"{page_url}: pagination repeated a page before completion")
                previous_pages.add(page_key)
                yield response
                parts = urlsplit(page_url)
                query = dict(parse_qsl(parts.query))
                query["start"] = str(int(query.get("start", "0")) + len(cards.cards))
                page_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
                continue
            if source.paginate and "disneycareers.com" in urlsplit(url).netloc and "json" in response.content_type:
                payload = json.loads(response.text)
                html = payload.get("results")
                if not isinstance(html, str) or not response_has_job_signal(html, "text/html"):
                    raise ValueError(f"{page_url}: Disney returned unreadable job results")
                yield FetchResult(response.requested_url, response.final_url, "text/html", html)
                current = re.search(r'data-current-page="(\d+)"', html)
                total_pages = re.search(r'data-total-pages="(\d+)"', html)
                if not current or not total_pages:
                    raise ValueError(f"{page_url}: Disney omitted pagination metadata")
                page = int(current.group(1))
                if page >= int(total_pages.group(1)):
                    return
                if str(page) in previous_pages:
                    raise ValueError(f"{page_url}: pagination repeated a page before completion")
                previous_pages.add(str(page))
                parts = urlsplit(page_url)
                query = dict(parse_qsl(parts.query))
                query["CurrentPage"] = str(page + 1)
                page_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
                continue
            if not response_has_job_signal(response.text, response.content_type):
                raise ValueError(f"{url}: response contained no job records or explicit zero-result state")
            if not source.paginate:
                yield response
                return
            if source.request_method == "GET" and "json" not in response.content_type.casefold():
                if page_url in previous_pages:
                    raise ValueError(f"{page_url}: pagination repeated a page before completion")
                previous_pages.add(page_url)
                yield response
                parser = CareerHTMLParser()
                parser.feed(response.text)
                next_link = next((href for href, label in parser.anchors if label.casefold() in {"next", "next page"}), None)
                if not next_link:
                    return
                from urllib.parse import urljoin
                page_url = urljoin(response.final_url, next_link)
                continue
            request_body = json.loads(body)
            payload = json.loads(response.text)
            rows = payload.get("jobPostings")
            reported_total = payload.get("total", payload.get("maxCount"))
            if not isinstance(rows, list) or not isinstance(reported_total, int) or reported_total < 0:
                raise ValueError(f"{url}: invalid paginated job response")
            # Workday reports total=0 on later pages even while returning jobs.
            if total is None:
                total = reported_total
                if rows and total < len(rows):
                    raise ValueError(f"{url}: invalid first-page job count")
            offset_key = "paginationStart" if "paginationStart" in request_body else "offset"
            offset = request_body.get(offset_key, 0)
            if not rows and offset < total:
                raise ValueError(f"{url}: empty page before all {total} jobs were scanned")
            page_key = json.dumps(rows, sort_keys=True)
            if rows and page_key in previous_pages:
                raise ValueError(f"{url}: pagination repeated a page before completion")
            previous_pages.add(page_key)
            yield response
            if offset + len(rows) >= total:
                return
            request_body[offset_key] = offset + len(rows)
            body = json.dumps(request_body)
        raise ValueError(f"{url}: pagination exceeded 50 pages; scan incomplete")

    @staticmethod
    def _print_dry_run(jobs: tuple[Job, ...]) -> None:
        if not jobs:
            print("Dry run found no matching roles.")
            return
        print(f"Dry run found {len(jobs)} matching role(s):")
        for job in sorted(jobs, key=lambda item: (item.company, item.title)):
            location = f" — {job.location}" if job.location else ""
            print(f"- {job.company}: {job.title}{location}\n  {job.url}")
