import subprocess
import unittest
from unittest.mock import patch

from apm_notifier.fetch import BrowserRenderer


class BrowserRendererTests(unittest.TestCase):
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
