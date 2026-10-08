import subprocess
import io
import unittest
from unittest.mock import patch, MagicMock

from apm_notifier.fetch import BrowserRenderer, HttpClient
from urllib.request import Request


class BrowserRendererTests(unittest.TestCase):
    def test_dayforce_search_bootstraps_anonymous_csrf_session(self) -> None:
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = io.BytesIO(b'{"csrfToken":"public-test-token"}')
        request = Request("https://jobs.dayforcehcm.com/api/geo/qfg/jobposting/search", data=b'{}', method="POST")
        with patch("apm_notifier.fetch.build_opener", return_value=opener):
            HttpClient(5)._open_request(request)
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(request.get_header("X-csrf-token"), "public-test-token")

    def test_retries_a_transient_browser_timeout(self) -> None:
        renderer = BrowserRenderer(5)
        renderer.executable = "/bin/true"
        success = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='<a href="/jobs/1">Product Manager Intern</a>',
            stderr="",
        )
        with (
            patch(
                "apm_notifier.fetch.subprocess.run",
                side_effect=(subprocess.TimeoutExpired("chromium", 5), success),
            ) as run,
            patch("apm_notifier.fetch.time.sleep"),
        ):
            result = renderer.fetch("https://jobs.example.com")

        self.assertEqual(run.call_count, 2)
        self.assertIn("Product Manager Intern", result.text)


if __name__ == "__main__":
    unittest.main()
