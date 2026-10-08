from pathlib import Path
import json
import tempfile
import unittest

from apm_notifier.filtering import RoleFilter
from apm_notifier.models import FetchResult, Source, SourceResult
from apm_notifier.monitor import Monitor
from apm_notifier.notify import NotificationOutcome
from apm_notifier.state import StateStore


class FakeClient:
    timeout_seconds = 5

    def fetch(self, url, extra_headers=None, method="GET", body=""):
        return FetchResult(
            requested_url=url,
            final_url=url,
            content_type="text/html",
            text='<a href="/jobs/123">Product Manager Intern — Summer 2027 — New York</a>',
        )


class FakeNotifier:
    configured_channels = ("fake",)

    def __init__(self):
        self.sent = []

    def send_job(self, job):
        self.sent.append(job)
        return NotificationOutcome(delivered=True)

    def send_health(self, result):
        return NotificationOutcome(delivered=True)


class GraduateClient:
    timeout_seconds = 5

    def __init__(self, details):
        self.details = details

    def fetch(self, url, extra_headers=None, method="GET", body=""):
        if url.endswith("/7673256057754290437"):
            text = self.details
        else:
            text = """
            <a href="https://lifeattiktok.com/search/7673256057754290437">
              <span>Creative Product Manager Graduate - 2027 Start</span>
              <span>San Jose</span><span>Product</span>
            </a>
            """
        return FetchResult(
            requested_url=url,
            final_url=url,
            content_type="text/html",
            text=text,
        )


class MonitorTests(unittest.TestCase):
    def test_scans_later_pages_and_rejects_repeated_pages(self) -> None:
        for offset_key, total_key in (("offset", "total"), ("paginationStart", "maxCount")):
            for repeated in (False, True):
                with self.subTest(offset_key=offset_key, repeated=repeated):
                    source = Source(
                        id="example", name="Example", urls=("https://jobs.example.com/api",),
                        career_url="https://jobs.example.com", request_method="POST", paginate=True,
                        request_bodies=(json.dumps({offset_key: 0, "limit": 1}),),
                    )
                    class PagedClient:
                        timeout_seconds = 5
                        def fetch(self, url, extra_headers=None, method="GET", body=""):
                            offset = json.loads(body)[offset_key]
                            title = "Senior Product Manager" if offset < 2 or repeated else "Product Manager: New Grad Accelerator"
                            reported_total = 0 if total_key == "total" and offset else 3
                            payload = {total_key: reported_total, "jobPostings": [{"title": title, "url": "/jobs/1" if repeated else f"/jobs/{offset + 1}", "location": "New York"}]}
                            return FetchResult(url, url, "application/json", json.dumps(payload))
                    monitor = Monitor((source,), PagedClient(), RoleFilter(2027, (2026,)), None, None, 1, False)
                    result = monitor._check_source(source)
                    self.assertEqual(result.succeeded, not repeated)
                    self.assertEqual(len(result.jobs), 0 if repeated else 1)
                    if repeated:
                        self.assertIn("repeated a page", result.errors[0])

    def test_partial_source_fetch_is_not_healthy(self) -> None:
        source = Source(
            id="example",
            name="Example",
            urls=("https://jobs.example.com/one", "https://jobs.example.com/two"),
            career_url="https://jobs.example.com/",
        )
        result = SourceResult(source=source, jobs=(), fetched_urls=1, errors=("second failed",))
        self.assertFalse(result.succeeded)

    def test_delivers_each_job_only_once(self) -> None:
        source = Source(
            id="example",
            name="Example",
            urls=("https://jobs.example.com/search",),
            career_url="https://jobs.example.com/",
        )
        notifier = FakeNotifier()
        with tempfile.TemporaryDirectory() as directory:
            store = StateStore(Path(directory) / "state.sqlite3")
            try:
                monitor = Monitor(
                    sources=(source,),
                    client=FakeClient(),
                    role_filter=RoleFilter(2027, (2024, 2025, 2026)),
                    store=store,
                    notifier=notifier,
                    concurrency=1,
                    alert_on_first_run=True,
                )
                first = monitor.run_once()
                second = monitor.run_once()
                self.assertEqual(first.alerts_delivered, 1)
                self.assertEqual(second.alerts_delivered, 0)
                self.assertEqual(len(notifier.sent), 1)
                self.assertEqual(store.pending_jobs(), ())
            finally:
                store.close()

    def test_suppresses_masters_only_graduate_role_after_detail_check(self) -> None:
        source = Source(
            id="tiktok",
            name="TikTok",
            urls=("https://lifeattiktok.com/search?keyword=product-manager-graduate",),
            career_url="https://lifeattiktok.com/",
            verify_graduate_education=True,
        )
        client = GraduateClient(
            "Minimum Qualifications: Applicants must be completing a Master's degree."
        )
        monitor = Monitor(
            sources=(source,),
            client=client,
            role_filter=RoleFilter(2027, (2024, 2025, 2026)),
            store=None,
            notifier=None,
            concurrency=1,
            alert_on_first_run=True,
        )

        result = monitor._check_source(source)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.jobs, ())


if __name__ == "__main__":
    unittest.main()
