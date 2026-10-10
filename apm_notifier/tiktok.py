from __future__ import annotations

import json
from urllib.parse import urlsplit

from .models import FetchResult


SEARCH_PATH = "/api/v1/public/supplier/search/job/posts"


def normalize_search_response(response: FetchResult) -> FetchResult:
    """Validate TikTok's public search API before using its total for pagination."""
    parts = urlsplit(response.requested_url)
    if parts.hostname != "api.lifeattiktok.com" or parts.path != SEARCH_PATH:
        return response
    payload = json.loads(response.text)
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise ValueError("TikTok search API returned an error response")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("TikTok search API omitted job data")
    rows, count = data.get("job_post_list"), data.get("count")
    if not isinstance(rows, list) or type(count) is not int or count < 0:
        raise ValueError("TikTok search API omitted valid jobs or pagination count")
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("title"), str)
        or not row["title"].strip()
        or not row.get("id")
        for row in rows
    ):
        raise ValueError("TikTok search API returned an unreadable job record")
    return FetchResult(
        requested_url=response.requested_url,
        final_url=response.final_url,
        content_type="application/json",
        text=json.dumps({"jobPostings": rows, "total": count}),
    )
