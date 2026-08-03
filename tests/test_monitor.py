from pathlib import Path
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


class MonitorTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
