from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {
    "gh_src",
    "lever-source",
    "source",
    "src",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def canonical_url(value: str) -> str:
    """Remove fragments and common tracking parameters without changing job IDs."""
    parts = urlsplit(value)
    query = [
        (key, item)
        for key, item in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/") or "/",
            urlencode(query),
            "",
        )
    )


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    urls: tuple[str, ...]
    career_url: str
    enabled: bool = True
    headers: dict[str, str] = field(default_factory=dict)
    url_template: str = ""
    render: bool = False
    request_method: str = "GET"
    request_bodies: tuple[str, ...] = ()
    verify_job_links: bool = False
    verify_graduate_education: bool = False
    include_adjacent_marketing: bool = False


@dataclass(frozen=True)
class Job:
    source_id: str
    company: str
    title: str
    url: str
    location: str = ""
    discovered_at: str = field(default_factory=utc_now)

    @property
    def fingerprint(self) -> str:
        material = "|".join(
            (
                normalize_space(self.company).casefold(),
                normalize_space(self.title).casefold(),
                canonical_url(self.url),
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class FetchResult:
    requested_url: str
    final_url: str
    content_type: str
    text: str


@dataclass(frozen=True)
class SourceResult:
    source: Source
    jobs: tuple[Job, ...]
    fetched_urls: int
    errors: tuple[str, ...] = ()

    @property
    def succeeded(self) -> bool:
        return self.fetched_urls == len(self.source.urls) and not self.errors
