from dataclasses import replace
import json
from pathlib import Path
import unittest

from apm_notifier.config import load_sources
from apm_notifier.filtering import RoleFilter
from apm_notifier.models import FetchResult
from apm_notifier.monitor import Monitor
from apm_notifier.tiktok import normalize_search_response


API = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"


def api_response(rows, count, code=0):
    return FetchResult(API, API, "application/json", json.dumps({
        "code": code, "data": {"job_post_list": rows, "count": count},
    }))


def posting(identifier, title, city="San Jose", country="United States of America", requirements="Minimum Qualifications:\n- Completing a Bachelor's degree."):
    return {
        "id": identifier, "title": title, "requirement": requirements,
        "city_info": {"name": None, "en_name": city, "i18n_name": city,
                      "parent": {"name": None, "en_name": country, "location_type": 1}},
    }


class TikTokTests(unittest.TestCase):
    def setUp(self):
        self.source = next(s for s in load_sources(Path(__file__).resolve().parent.parent / "config/sources.json") if s.id == "tiktok")
        self.filter = RoleFilter(2027, (2026,))

    def test_configuration_scans_campus_and_unrestricted_graduate_search(self):
        self.assertFalse(self.source.render)
        self.assertTrue(self.source.paginate)
        self.assertTrue(self.source.priority)
        self.assertTrue(self.source.include_adjacent_marketing)
        bodies = [json.loads(body) for body in self.source.request_bodies]
        self.assertTrue(any(body["keyword"] == "graduate" and not body["recruitment_id_list"] for body in bodies))
        self.assertTrue(any(not body["keyword"] and body["recruitment_id_list"] == ["2"] for body in bodies))
        self.assertTrue(all(not body["location_code_list"] and not body["job_category_id_list"] for body in bodies))

    def test_missing_role_families_on_later_pages_are_detected_with_inline_qualifications(self):
        expected = {
            "7673335985398106373": "Global Product Strategy & Operation Graduate (Scaled Growth) - 2027 Start",
            "7673200904214300933": "Product Solutions and Operations Graduate (Commerce Ads) - 2027 Start",
            "7667573398700165429": "POI Content Product Manager Graduate (TikTok Local Services) - 2027 Start",
            "7675439423287314693": "Product Manager Graduate (Scaled Growth) - 2027 Start",
            "7676465555633932597": "Account Manager Graduate (GBS) - 2027 Summer",
            "7667571412695517445": "Dine-In Campaign Graduate (TikTok Local Services) - 2027 Start",
        }
        rows = [posting(str(i), "Senior Product Manager") for i in range(12)]
        rows += [posting(identifier, title) for identifier, title in expected.items()]
        rows += [
            posting("masters", "Creative Product Manager Graduate - 2027 Start", requirements="Minimum Qualifications:\n- Completing a Master’s degree in Business."),
            posting("mba", "Campaign Graduate - 2027 Start (MBA)"),
            posting("old", "Product Manager Graduate - 2026 Start"),
            posting("outside", "Product Manager Graduate - 2027 Start", city="Singapore", country="Singapore"),
            posting("australia", "Product Manager Graduate - 2027 Start", city="Sydney, New South Wales", country="Australia"),
        ]
        class Client:
            timeout_seconds = 5
            def __init__(self):
                self.offsets = []
            def fetch(self, url, extra_headers=None, method="GET", body=""):
                # Every matching qualification is supplied by the API; no detail round-trips.
                if url != API:
                    raise AssertionError("Unexpected job detail fetch")
                offset = json.loads(body)["offset"]
                self.offsets.append(offset)
                return api_response(rows[offset:offset + 12], len(rows))
        client = Client()
        result = Monitor((self.source,), client, self.filter, None, None, 1, True)._check_source(self.source)
        self.assertTrue(result.succeeded, result.errors)
        self.assertEqual({j.url.rsplit("/", 1)[-1] for j in result.jobs}, set(expected))
        self.assertEqual(client.offsets, [0, 12, 0, 12])
        self.assertTrue(all("United States of America" in j.location for j in result.jobs))

    def test_api_errors_are_not_healthy_empty_results(self):
        for payload in ({"code": 1, "data": {"job_post_list": [], "count": 0}},
                        {"code": 0, "data": None},
                        {"code": 0, "data": {"job_post_list": [], "count": None}},
                        {"code": 0, "data": {"job_post_list": [{}], "count": 1}}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                normalize_search_response(FetchResult(API, API, "application/json", json.dumps(payload)))

    def test_incomplete_or_repeated_pages_report_failure(self):
        source = replace(self.source, urls=(API,), request_bodies=(self.source.request_bodies[0],))
        for repeated in (False, True):
            class Client:
                timeout_seconds = 5
                def fetch(self, url, extra_headers=None, method="GET", body=""):
                    rows = [posting("one", "Product Growth Graduate - 2027 Start")]
                    if json.loads(body)["offset"] and not repeated:
                        rows = []
                    return api_response(rows, 2)
            result = Monitor((source,), Client(), self.filter, None, None, 1, True)._check_source(source)
            self.assertFalse(result.succeeded)
            self.assertEqual(len(result.jobs), 1)

    def test_explicit_empty_api_result_is_healthy(self):
        class Client:
            timeout_seconds = 5
            def fetch(self, url, extra_headers=None, method="GET", body=""):
                return api_response([], 0)
        result = Monitor((self.source,), Client(), self.filter, None, None, 1, True)._check_source(self.source)
        self.assertTrue(result.succeeded, result.errors)
        self.assertEqual(result.jobs, ())
