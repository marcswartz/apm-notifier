import json
import unittest

from apm_notifier.extract import extract_jobs, response_has_job_signal
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

    def test_extracts_opted_in_adjacent_marketing_role(self) -> None:
        source = Source(
            id="mastercard",
            name="Mastercard",
            urls=("https://careers.example.com/search",),
            career_url="https://careers.example.com/",
            include_adjacent_marketing=True,
        )
        payload = {
            "jobs": [
                {
                    "title": "Partner Marketing Specialist",
                    "applyUrl": "https://careers.example.com/jobs/R-288655",
                    "location": "Toronto, Ontario, Canada",
                }
            ]
        }
        jobs = extract_jobs(
            json.dumps(payload),
            "application/json",
            source,
            "https://careers.example.com/search",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Partner Marketing Specialist")

    def test_extracts_ashby_embedded_job_board(self) -> None:
        source = Source(
            id="lime",
            name="Lime",
            urls=("https://jobs.ashbyhq.com/Lime?embed=js",),
            career_url="https://www.li.me/about/careers",
            url_template="https://jobs.ashbyhq.com/Lime/{id}",
            include_adjacent_marketing=True,
        )
        html = """
        <script>
        window.__appData = {"jobBoard":{"jobPostings":[
          {"id":"lime-123","title":"Marketing Intern — Summer 2027",
           "locationName":"Toronto, Canada"}
        ]}};
        </script>
        """
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            source,
            "https://jobs.ashbyhq.com/Lime?embed=js",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "Toronto, Canada")
        self.assertEqual(jobs[0].url, "https://jobs.ashbyhq.com/Lime/lime-123")

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

    def test_cleans_microsoft_rendered_job_card(self) -> None:
        html = """
        <a href="/careers/job/1970393556953113">
          Product Manager: Internship Opportunities
          United States, Washington, Redmond
          Posted 16 hours ago
        </a>
        """
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://apply.careers.microsoft.com/careers?query=product",
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

    def test_extracts_lever_location_from_categories(self) -> None:
        payload = [
            {
                "text": "Product Marketing Intern — Summer 2027",
                "hostedUrl": "https://jobs.lever.co/example/pm-1",
                "categories": {"team": "Marketing", "location": "London, UK"},
            }
        ]
        jobs = extract_jobs(
            json.dumps(payload),
            "application/json",
            self.source,
            "https://api.lever.co/v0/postings/example",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "London, UK")

    def test_extracts_workday_job_with_public_url_template(self) -> None:
        source = Source(
            id="salesforce",
            name="Salesforce",
            urls=("https://example.wd/jobs",),
            career_url="https://example.com/careers",
            url_template="https://example.wd/Careers/{path}",
        )
        payload = {
            "jobPostings": [
                {
                    "title": "Associate Product Manager (starting summer 2027)",
                    "externalPath": "/job/San-Francisco/APM_123",
                    "locationsText": "California - San Francisco",
                }
            ]
        }
        jobs = extract_jobs(
            json.dumps(payload),
            "application/json",
            source,
            "https://example.wd/jobs",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].url, "https://example.wd/Careers/job/San-Francisco/APM_123")

    def test_extracts_company_from_community_markdown_table(self) -> None:
        markdown = """
        | Company | Role | Location | Apply | Added |
        | --- | --- | --- | --- | --- |
        | Databricks | Product Management Intern (Summer 2027) | San Francisco, CA | [apply](https://example.com/db) | 2026-07-16 |
        | Salesforce | Associate Product Manager Intern 🔒 | San Francisco, CA | [apply](https://example.com/sf) | - |
        | Other | Software Engineer Intern | Seattle, WA | [apply](https://example.com/swe) | - |
        """
        jobs = extract_jobs(markdown, "text/plain", self.source, self.source.career_url, self.filter)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Databricks")
        self.assertEqual(jobs[0].url, "https://example.com/db")

    def test_job_signal_rejects_empty_spa_shell(self) -> None:
        self.assertFalse(response_has_job_signal("<html><a href='/careers'>Careers</a></html>", "text/html"))
        self.assertTrue(
            response_has_job_signal(
                "<html><a href='/jobs/123'>Product Manager Intern</a></html>",
                "text/html",
            )
        )
        self.assertTrue(response_has_job_signal('{"jobs": []}', "application/json"))

    def test_extracts_rendered_yc_product_card(self) -> None:
        html = """
        <div class="flex cursor-pointer flex-col">
          <div><img class="logo" alt="Dedalus Labs"></div>
          <div><a href="/jobs/98000" target="job">Product Manager Summer 2027 Intern</a></div>
          <div><p class="job-details">
            <span>Intern</span><span>San Francisco, CA, US</span><span>$4K monthly</span>
          </p></div>
        </div>
        """
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://www.workatastartup.com/jobs/l/product-manager",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].company, "Dedalus Labs")
        self.assertEqual(jobs[0].location, "San Francisco, CA, US")
        self.assertEqual(jobs[0].url, "https://www.workatastartup.com/jobs/98000")

    def test_extracts_rendered_meta_job_card(self) -> None:
        html = """
        <a href="/profile/job_details/123" target="_blank">
          <div><h3>Rotational Product Manager — 2027</h3></div>
          <div><span>Menlo Park, CA</span><span>Product Management</span></div>
        </a>
        """
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://www.metacareers.com/jobsearch/",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Rotational Product Manager — 2027")
        self.assertEqual(jobs[0].location, "Menlo Park, CA")
        self.assertEqual(jobs[0].url, "https://www.metacareers.com/profile/job_details/123")

    def test_extracts_clean_tiktok_graduate_job_card(self) -> None:
        html = """
        <a href="https://lifeattiktok.com/search/7673256057754290437">
          <div><span class="font-bold">
            Creative Product Manager Graduate (Creative and Brand Innovation) - 2027 Start
          </span></div>
          <div>
            <span>San Jose</span><span>Product - Product manager</span>
            <span>Regular</span><span>Bachelor/Master</span>
          </div>
        </a>
        """
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://lifeattiktok.com/search?keyword=product%20manager%20graduate",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(
            jobs[0].title,
            "Creative Product Manager Graduate (Creative and Brand Innovation) - 2027 Start",
        )
        self.assertEqual(jobs[0].location, "San Jose")
        self.assertEqual(
            jobs[0].url,
            "https://lifeattiktok.com/search/7673256057754290437",
        )

    def test_extracts_rendered_walmart_job_card(self) -> None:
        html = """
        <div data-testid="job-card" data-job-id="WD-123" role="link">
          <div><span data-testid="job-title">Product Marketing Intern — Summer 2027</span></div>
          <div><span data-testid="category">Marketing</span><span>Hoboken, NJ</span></div>
        </div>
        """
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://careers.walmart.com/us/en/results?searchQuery=product%20marketing%20intern",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].location, "Hoboken, NJ")
        self.assertTrue(jobs[0].url.endswith("#WD-123"))

    def test_extracts_ea_avature_job_card_with_location(self) -> None:
        html = """
        <article class="article article--result article--non-toggle">
          <h3>
            <a class="link link_result" href="https://jobs.ea.com/en_US/careers/JobDetail/Product-Manager-Intern/123">
              Product Manager Intern — Summer 2027
            </a>
          </h3>
          <div class="article__header__text__subtitle">
            <span class="list-item-location">Vancouver, Canada</span>
            <span class="list-item-id">Role ID 123</span>
          </div>
        </article>
        """
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://jobs.ea.com/en_US/careers/SearchJobs/?search=product",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Product Manager Intern — Summer 2027")
        self.assertEqual(jobs[0].location, "Vancouver, Canada")
        self.assertTrue(jobs[0].url.endswith("/Product-Manager-Intern/123"))

    def test_extracts_shopify_react_router_job_feed(self) -> None:
        devalue_payload = [
            {"_1": 2},
            "loaderData",
            {"_3": 4},
            "($locale)/careers",
            {"_5": 6},
            "jobPostingsWithJobs",
            [7],
            {"_8": 9},
            "jobPosting",
            {"_10": 11, "_12": 13, "_14": 15},
            "title",
            "Product Marketing Intern — Summer 2027",
            "locationName",
            "Toronto, Canada",
            "externalLink",
            "https://www.shopify.com/careers?ashby_jid=shopify-123",
        ]
        serialized_chunk = json.dumps(json.dumps(devalue_payload))
        html = (
            "<script>window.__reactRouterContext.streamController.enqueue("
            f"{serialized_chunk});</script>"
        )
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://www.shopify.com/careers",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Product Marketing Intern — Summer 2027")
        self.assertEqual(jobs[0].location, "Toronto, Canada")
        self.assertEqual(
            jobs[0].url,
            "https://www.shopify.com/careers?ashby_jid=shopify-123",
        )

    def test_extracts_google_init_data_without_browser_rendering(self) -> None:
        matching_row = [
            "123456789012345678",
            "Product Manager Intern — Summer 2027",
            "https://www.google.com/about/careers/applications/signin?jobId=token",
            None,
            None,
            None,
            None,
            "Google",
            "en-US",
            [["Toronto, ON, Canada", ["111 Richmond St W, Toronto, ON"], "Toronto"]],
        ]
        unrelated_row = [
            "876543210987654321",
            "Senior Product Manager",
            "https://www.google.com/about/careers/applications/signin?jobId=other",
            None,
            None,
            None,
            None,
            "Google",
            "en-US",
            [["Mountain View, CA, USA"]],
        ]
        payload = json.dumps([[matching_row, unrelated_row], None, 2, 2])
        html = (
            "<script>AF_initDataCallback({key: 'ds:1', hash: '2', data:"
            f"{payload}"
            "});</script>"
        )
        self.assertTrue(response_has_job_signal(html, "text/html"))
        jobs = extract_jobs(
            html,
            "text/html",
            self.source,
            "https://www.google.com/about/careers/applications/jobs/results/?q=product",
            self.filter,
        )
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Product Manager Intern — Summer 2027")
        self.assertEqual(jobs[0].location, "Toronto, ON, Canada")
        self.assertEqual(
            jobs[0].url,
            "https://www.google.com/about/careers/applications/jobs/results/123456789012345678",
        )

    def test_google_empty_results_are_still_a_healthy_response(self) -> None:
        html = (
            "<script>AF_initDataCallback("
            "{key: 'ds:1', hash: '2', data:[[],null,0,0]});</script>"
        )
        self.assertTrue(response_has_job_signal(html, "text/html"))


if __name__ == "__main__":
    unittest.main()
