from __future__ import annotations

from html.parser import HTMLParser
from html import unescape
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin

from .filtering import RoleFilter
from .models import Job, Source, normalize_space


TITLE_KEYS = ("title", "jobTitle", "job_title", "postingTitle", "posting_title", "posting_name", "name", "text")
URL_KEYS = (
    "canonicalPositionUrl",
    "positionUrl",
    "job_path",
    "url_next_step",
    "url",
    "absolute_url",
    "hostedUrl",
    "jobUrl",
    "job_url",
    "applyUrl",
    "externalPath",
    "external_path",
    "ref",
)
LOCATION_KEYS = ("location", "jobLocation", "job_location", "locations", "city")
MICROSOFT_RENDERED_JOB = re.compile(
    r"^(?P<title>.+?)\s+(?P<location>(?:United States|Canada|United Kingdom),.+?)"
    r"\s+Posted\s+.+$",
    re.IGNORECASE,
)


class CareerHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[tuple[str, str]] = []
        self.json_scripts: list[str] = []
        self.json_code_blocks: list[str] = []
        self._anchor_href: str | None = None
        self._anchor_text: list[str] = []
        self._anchor_label = ""
        self._in_script = False
        self._script_type = ""
        self._script_text: list[str] = []
        self._in_code = False
        self._code_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "a" and self._anchor_href is None:
            self._anchor_href = attributes.get("href", "")
            self._anchor_label = attributes.get("aria-label") or attributes.get("title") or ""
            self._anchor_text = []
        if tag.casefold() == "script":
            self._in_script = True
            self._script_type = attributes.get("type", "")
            self._script_text = []
        if tag.casefold() == "code":
            self._in_code = True
            self._code_text = []

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._anchor_text.append(data)
        if self._in_script:
            self._script_text.append(data)
        if self._in_code:
            self._code_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._anchor_href is not None:
            label = normalize_space(" ".join(self._anchor_text)) or normalize_space(self._anchor_label)
            if self._anchor_href and label:
                self.anchors.append((self._anchor_href, label))
            self._anchor_href = None
            self._anchor_text = []
            self._anchor_label = ""
        if tag.casefold() == "script" and self._in_script:
            script = "".join(self._script_text).strip()
            if script and ("json" in self._script_type.casefold() or script[:1] in {"{", "["}):
                self.json_scripts.append(script)
            self._in_script = False
            self._script_type = ""
            self._script_text = []
        if tag.casefold() == "code" and self._in_code:
            block = unescape("".join(self._code_text)).strip()
            if block[:1] in {"{", "["}:
                self.json_code_blocks.append(block)
            self._in_code = False
            self._code_text = []


def _first_string(item: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, (str, int)):
            return normalize_space(str(value))
    return ""


def _location_text(value: Any) -> str:
    if isinstance(value, str):
        return normalize_space(value)
    if isinstance(value, list):
        parts = [_location_text(item) for item in value]
        return "; ".join(part for part in parts if part)[:300]
    if isinstance(value, dict):
        direct = _first_string(value, ("name", "location", "formattedAddress", "city", "addressLocality"))
        if direct:
            return direct
        address = value.get("address")
        if address is not None:
            return _location_text(address)
    return ""


def _walk_json(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _jobs_from_json(
    payload: Any,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    jobs: list[Job] = []
    for item in _walk_json(payload):
        title = _first_string(item, TITLE_KEYS)
        if not role_filter.matches(title):
            continue
        identifier = _first_string(item, ("id", "jobId", "job_id", "requisitionId"))
        if source.url_template and identifier:
            url = source.url_template.format(id=identifier)
        else:
            url = _first_string(item, URL_KEYS)
        if not url:
            url = f"{source.career_url}#{identifier}" if identifier else source.career_url
        location = ""
        for key in LOCATION_KEYS:
            if key in item:
                location = _location_text(item[key])
                if location:
                    break
        if not role_filter.matches_location(location, title):
            continue
        jobs.append(
            Job(
                source_id=source.id,
                company=source.name,
                title=title,
                url=urljoin(base_url, url),
                location=location,
            )
        )
    return jobs


def _json_object_after(text: str, marker: str) -> Any | None:
    """Decode a JSON object assigned inside a larger JavaScript block."""
    marker_at = text.find(marker)
    if marker_at < 0:
        return None
    start = text.find("{", marker_at + len(marker))
    if start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def extract_jobs(
    text: str,
    content_type: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> tuple[Job, ...]:
    jobs: list[Job] = []
    stripped = text.lstrip()
    is_json = "json" in content_type.casefold() or stripped[:1] in {"{", "["}
    if is_json:
        try:
            jobs.extend(_jobs_from_json(json.loads(stripped), source, base_url, role_filter))
        except json.JSONDecodeError:
            pass
    else:
        parser = CareerHTMLParser()
        parser.feed(text)
        for href, label in parser.anchors:
            title = label
            location = ""
            if "apply.careers.microsoft.com" in base_url and "/careers/job/" in href:
                microsoft_match = MICROSOFT_RENDERED_JOB.match(label)
                if microsoft_match:
                    title = normalize_space(microsoft_match.group("title"))
                    location = normalize_space(microsoft_match.group("location"))
            if role_filter.matches(title) and role_filter.matches_location(location, title):
                jobs.append(
                    Job(
                        source_id=source.id,
                        company=source.name,
                        title=title,
                        url=urljoin(base_url, href),
                        location=location,
                    )
                )
        for script in parser.json_scripts:
            try:
                payload = json.loads(script)
            except json.JSONDecodeError:
                continue
            jobs.extend(_jobs_from_json(payload, source, base_url, role_filter))
        for block in parser.json_code_blocks:
            try:
                payload = json.loads(block)
            except json.JSONDecodeError:
                continue
            jobs.extend(_jobs_from_json(payload, source, base_url, role_filter))

        phenom_state = _json_object_after(text, "phApp.ddo =")
        if phenom_state is not None:
            jobs.extend(_jobs_from_json(phenom_state, source, base_url, role_filter))

    unique: dict[str, Job] = {}
    for job in jobs:
        unique[job.fingerprint] = job
    return tuple(unique.values())
