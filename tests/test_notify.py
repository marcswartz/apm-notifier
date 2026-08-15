import unittest

from apm_notifier.notify import _health_error_summary


class HealthErrorSummaryTests(unittest.TestCase):
    def test_collapses_repeated_http_errors_without_long_urls(self) -> None:
        errors = (
            "https://example.com/a?long=query: HTTP Error 503: Service Temporarily Unavailable",
            "https://example.com/b?long=query: HTTP Error 503: Service Temporarily Unavailable",
        )

        summary = _health_error_summary(errors)

        self.assertEqual(summary, "HTTP 503: Service Temporarily Unavailable")
        self.assertNotIn("https://", summary)

    def test_summarizes_browser_timeout(self) -> None:
        summary = _health_error_summary(
            ("https://example.com: browser render failed after retry: timed out",)
        )
        self.assertEqual(summary, "Browser rendering timed out after retries")


if __name__ == "__main__":
    unittest.main()
