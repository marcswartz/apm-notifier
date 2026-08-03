import json
import unittest

from apm_notifier.extract import extract_jobs
from apm_notifier.filtering import RoleFilter
from apm_notifier.models import Source


class ExtractJobsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Source(
            id="example",
            name="Example",
            urls=("https://jobs.example.com/search",),
            career_url="https://jobs.example.com/",
        )
        self.filter = RoleFilter(2027, (2024, 2025, 2026))

    def test_extracts_matching_anchor_only(self) -> None:
        html = """
        <html><body>
          <a href="/jobs/123">Product Manager Intern — Summer 2027 — New York</a>
          <a href="/jobs/456">Senior Product Manager</a>
        </body></html>
        """
        jobs = extract_jobs(html, "text/html", self.source, "https://jobs.example.com/search", self.filter)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://jobs.example.com/jobs/123")

    def test_extracts_nested_json_jobs(self) -> None:
        payload = {
            "results": [
                {
                    "jobTitle": "Product Marketing Intern 2027",
                    "externalPath": "/jobs/pm-7",
                    "location": {"name": "Toronto"},
                },
                {"jobTitle": "Senior Product Marketing Manager", "externalPath": "/jobs/pm-8"},
            ]
        }
        jobs = extract_jobs(
            json.dumps(payload),
            "application/json",
            self.source,
            "https://jobs.example.com/api/search",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "Toronto")
        self.assertEqual(jobs[0].url, "https://jobs.example.com/jobs/pm-7")

    def test_extracts_microsoft_positions_api_job(self) -> None:
        payload = {
            "data": {
                "positions": [
                    {
                        "id": 1970393556953113,
                        "name": "Product Manager: Internship Opportunities",
                        "locations": ["United States, Washington, Redmond"],
                        "positionUrl": "/careers/job/1970393556953113",
                    },
                    {
                        "id": 1970393556928915,
                        "name": "Senior Product Manager / Product Manager",
                        "locations": ["United States, Washington, Redmond"],
                        "positionUrl": "/careers/job/1970393556928915",
                    },
                ]
            }
        }
        jobs = extract_jobs(
            json.dumps(payload),
            "application/json",
            self.source,
            "https://apply.careers.microsoft.com/api/pcsx/search",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Product Manager: Internship Opportunities")
        self.assertEqual(jobs[0].location, "United States, Washington, Redmond")
        self.assertEqual(
            jobs[0].url,
            "https://apply.careers.microsoft.com/careers/job/1970393556953113",
        )

    def test_rejects_matching_job_outside_allowed_countries(self) -> None:
        payload = {
            "results": [
                {
                    "jobTitle": "Product Marketing Intern 2027",
                    "externalPath": "/jobs/singapore",
                    "location": "SG, Singapore",
                },
                {
                    "jobTitle": "Product Marketing Intern 2027",
                    "externalPath": "/jobs/canada",
                    "location": "Toronto, Canada",
                },
            ]
        }
        jobs = extract_jobs(
            json.dumps(payload),
            "application/json",
            self.source,
            "https://jobs.example.com/api/search",
            self.filter,
        )
        self.assertEqual([job.url for job in jobs], ["https://jobs.example.com/jobs/canada"])

    def test_extracts_json_ld_job_posting(self) -> None:
        payload = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Associate Product Manager",
            "url": "https://jobs.example.com/jobs/apm",
            "jobLocation": {"address": {"addressLocality": "New York"}},
        }
        html = f'<script type="application/ld+json">{json.dumps(payload)}</script>'
        jobs = extract_jobs(html, "text/html", self.source, "https://jobs.example.com", self.filter)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "New York")

    def test_extracts_eightfold_code_block(self) -> None:
        payload = {
            "positions": [
                {
                    "name": "Product Manager Intern 2027",
                    "canonicalPositionUrl": "https://jobs.example.com/jobs/ef-1",
                    "location": "Remote - US",
                }
            ]
        }
        encoded = json.dumps(payload).replace('"', "&#34;")
        html = f'<code id="smartApplyData" style="display:none">{encoded}</code>'
        jobs = extract_jobs(html, "text/html", self.source, "https://jobs.example.com", self.filter)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://jobs.example.com/jobs/ef-1")

    def test_extracts_phenom_assignment(self) -> None:
        payload = {
            "data": {
                "jobs": [
                    {
                        "title": "Product Marketing Intern — 2027",
                        "applyUrl": "https://jobs.example.com/jobs/ph-1",
                        "city": "Toronto",
                    }
                ]
            }
        }
        html = f"<script>var phApp = {{}}; phApp.ddo = {json.dumps(payload)}; phApp.experimentData = {{}};</script>"
        jobs = extract_jobs(html, "text/html", self.source, "https://jobs.example.com", self.filter)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://jobs.example.com/jobs/ph-1")


if __name__ == "__main__":
    unittest.main()
