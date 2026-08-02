from pathlib import Path
import tempfile
import unittest

from apm_notifier.models import Job
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


if __name__ == "__main__":
    unittest.main()
