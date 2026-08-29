from __future__ import annotations

from html.parser import HTMLParser
from html import unescape
import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin

from .filtering import RoleFilter
from .models import Job, Source, normalize_space


TITLE_KEYS = (
    "title",
    "Title",
    "jobTitle",
    "job_title",
    "postingTitle",
    "posting_title",
    "posting_name",
    "name",
    "text",
)
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
LOCATION_KEYS = (
    "location",
    "jobLocation",
    "job_location",
    "locations",
    "locationsText",
    "locationName",
    "primary_location",
    "offices",
    "city",
    "categories",
    "PrimaryLocation",
)
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


def _matches_title(role_filter: RoleFilter, title: str, source: Source) -> bool:
    return role_filter.matches(
        title,
        include_adjacent_marketing=source.include_adjacent_marketing,
    )


def _jobs_from_json(
    payload: Any,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    jobs: list[Job] = []
    for item in _walk_json(payload):
        title = _first_string(item, TITLE_KEYS)
        if not _matches_title(role_filter, title, source):
            continue
        identifier = _first_string(item, ("id", "Id", "jobId", "job_id", "requisitionId"))
        raw_url = _first_string(item, URL_KEYS)
        if source.url_template and (identifier or raw_url):
            url = source.url_template.format(id=identifier, path=raw_url.lstrip("/"))
        else:
            url = raw_url
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


MARKDOWN_LINK = re.compile(r"\[[^]]+\]\((?P<url>https?://[^)]+)\)")


def _plain_markdown(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    return normalize_space(value.replace("**", "").replace("`", ""))


def _jobs_from_markdown(text: str, source: Source, role_filter: RoleFilter) -> list[Job]:
    """Read the standard Company | Role | Location | Apply internship table."""
    jobs: list[Job] = []
    for line in text.splitlines():
        if not line.lstrip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            continue
        company, title, location, apply_cell = cells[:4]
        if company.casefold() in {"company", "---"} or set(company) <= {"-", ":", " "}:
            continue
        if "🔒" in title or "closed" in title.casefold():
            continue
        link = MARKDOWN_LINK.search(apply_cell)
        clean_company = _plain_markdown(company)
        clean_title = _plain_markdown(title)
        clean_location = _plain_markdown(location)
        if not link or not _matches_title(role_filter, clean_title, source):
            continue
        if not role_filter.matches_location(clean_location, clean_title):
            continue
        jobs.append(
            Job(
                source_id=source.id,
                company=clean_company,
                title=clean_title,
                url=link.group("url"),
                location=clean_location,
            )
        )
    return jobs


JOB_COLLECTION_KEYS = frozenset(
    {
        "jobs",
        "positions",
        "postings",
        "results",
        "jobPostings",
        "requisitionList",
        "content",
        "body",
    }
)
ZERO_RESULT_MARKERS = (
    "no jobs found",
    "no matching jobs",
    "no open positions",
    "no results found",
    "we couldn't find any",
    "we could not find any",
    "0 jobs",
    "0 results",
)
JOB_DETAIL_HREF = re.compile(
    r"/(?:profile/job_details|(?:careers/)?(?:job|jobs|details|positions|jobdetail))/(?:results/)?[^/?#\"']+",
    re.IGNORECASE,
)
NUMERIC_SEARCH_HREF = re.compile(r"/search/\d{6,}", re.IGNORECASE)
GOOGLE_INIT_DATA = re.compile(
    r"AF_initDataCallback\(\{key:\s*'ds:1'.*?data:\s*",
    re.DOTALL,
)


def _json_array_at(text: str, start: int) -> Any | None:
    """Decode a JSON array embedded inside a larger JavaScript expression."""
    array_start = text.find("[", start)
    if array_start < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(array_start, len(text)):
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
        elif character == "[":
            depth += 1
        elif character == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[array_start : index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _google_result_rows(text: str) -> list[Any] | None:
    match = GOOGLE_INIT_DATA.search(text)
    if not match:
        return None
    payload = _json_array_at(text, match.end())
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        return None
    return payload[0]


def response_has_job_signal(text: str, content_type: str) -> bool:
    """Reject blank application shells that would otherwise look like successful fetches."""
    stripped = text.lstrip()
    is_json = "json" in content_type.casefold() or stripped[:1] in {"{", "["}
    if is_json:
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return False
        if isinstance(payload, list):
            return not payload or any(isinstance(item, dict) for item in payload)
        return any(key in item for item in _walk_json(payload) for key in JOB_COLLECTION_KEYS)

    lowered = text.casefold()
    if any(marker in lowered for marker in ZERO_RESULT_MARKERS):
        return True
    if "| company | role | location |" in lowered:
        return True
    if 'data-testid="job-card"' in lowered:
        return True
    if "job-search-card" in lowered and "linkedin.com/jobs/view/" in lowered:
        return True
    if "jobpostingswithjobs" in lowered and "__reactroutercontext" in lowered:
        return True
    if _google_result_rows(text) is not None:
        return True
    parser = CareerHTMLParser()
    parser.feed(text)
    for script in (*parser.json_scripts, *parser.json_code_blocks):
        try:
            payload = json.loads(script)
        except json.JSONDecodeError:
            continue
        if any(key in item for item in _walk_json(payload) for key in JOB_COLLECTION_KEYS):
            return True
    phenom_state = _json_object_after(text, "phApp.ddo =")
    if phenom_state is not None and any(
        key in item for item in _walk_json(phenom_state) for key in JOB_COLLECTION_KEYS
    ):
        return True
    ashby_state = _json_object_after(text, "window.__appData =")
    if ashby_state is not None and any(
        key in item for item in _walk_json(ashby_state) for key in JOB_COLLECTION_KEYS
    ):
        return True
    return any(
        JOB_DETAIL_HREF.search(href) or NUMERIC_SEARCH_HREF.search(href)
        for href, _ in parser.anchors
    )


class LinkedInJobCardParser(HTMLParser):
    """Extract LinkedIn's own postings from the public guest-search cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str]] = []
        self._depth = 0
        self._href = ""
        self._in_title = False
        self._in_location = False
        self._title_parts: list[str] = []
        self._location_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        classes = attributes.get("class", "").split()
        if not self._depth and tag.casefold() == "div" and "job-search-card" in classes:
            self._depth = 1
            self._href = ""
            self._title_parts = []
            self._location_parts = []
            return
        if not self._depth:
            return
        if tag.casefold() == "div":
            self._depth += 1
        elif tag.casefold() == "a" and "base-card__full-link" in classes:
            self._href = attributes.get("href", "")
        elif tag.casefold() == "h3" and "base-search-card__title" in classes:
            self._in_title = True
        elif tag.casefold() == "span" and "job-search-card__location" in classes:
            self._in_location = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_location:
            self._location_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag.casefold() == "h3" and self._in_title:
            self._in_title = False
        elif tag.casefold() == "span" and self._in_location:
            self._in_location = False
        elif tag.casefold() == "div":
            self._depth -= 1
            if self._depth == 0:
                title = normalize_space(" ".join(self._title_parts))
                location = normalize_space(" ".join(self._location_parts))
                if self._href and title:
                    self.cards.append((title, location, self._href))


def _jobs_from_linkedin_cards(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    parser = LinkedInJobCardParser()
    parser.feed(text)
    return [
        Job(
            source_id=source.id,
            company=source.name,
            title=title,
            url=urljoin(base_url, href.split("?", 1)[0]),
            location=location,
        )
        for title, location, href in parser.cards
        if _matches_title(role_filter, title, source)
        and role_filter.matches_location(location, title)
    ]


class YCJobCardParser(HTMLParser):
    """Extract company, title, and location from rendered Work at a Startup cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str, str]] = []
        self._depth = 0
        self._company = ""
        self._href = ""
        self._title_parts: list[str] = []
        self._span_parts: list[str] = []
        self._current_span: list[str] | None = None
        self._in_job_anchor = False
        self._in_details = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        classes = attributes.get("class", "")
        if not self._depth and tag.casefold() == "div" and "cursor-pointer" in classes:
            self._depth = 1
            self._company = ""
            self._href = ""
            self._title_parts = []
            self._span_parts = []
            return
        if not self._depth:
            return
        if tag.casefold() == "div":
            self._depth += 1
        elif tag.casefold() == "img" and "logo" in classes:
            self._company = normalize_space(attributes.get("alt"))
        elif tag.casefold() == "a" and attributes.get("target") == "job":
            self._href = attributes.get("href", "")
            self._in_job_anchor = True
        elif tag.casefold() == "p" and "job-details" in classes:
            self._in_details = True
        elif tag.casefold() == "span" and self._in_details:
            self._current_span = []

    def handle_data(self, data: str) -> None:
        if self._in_job_anchor:
            self._title_parts.append(data)
        if self._current_span is not None:
            self._current_span.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag.casefold() == "a" and self._in_job_anchor:
            self._in_job_anchor = False
        elif tag.casefold() == "span" and self._current_span is not None:
            value = normalize_space(" ".join(self._current_span))
            if value:
                self._span_parts.append(value)
            self._current_span = None
        elif tag.casefold() == "p" and self._in_details:
            self._in_details = False
        elif tag.casefold() == "div":
            self._depth -= 1
            if self._depth == 0 and self._company and self._href and self._title_parts:
                location = self._span_parts[1] if len(self._span_parts) > 1 else ""
                self.cards.append(
                    (self._company, normalize_space(" ".join(self._title_parts)), location, self._href)
                )


def _jobs_from_yc_cards(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    parser = YCJobCardParser()
    parser.feed(text)
    return [
        Job(
            source_id=source.id,
            company=company,
            title=title,
            url=urljoin(base_url, href),
            location=location,
        )
        for company, title, location, href in parser.cards
        if _matches_title(role_filter, title, source)
        and role_filter.matches_location(location, title)
    ]


class MetaJobCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str]] = []
        self._href = ""
        self._in_title = False
        self._in_span = False
        self._title_parts: list[str] = []
        self._span_parts: list[str] = []
        self._current_span: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if tag.casefold() == "a" and "/profile/job_details/" in attributes.get("href", ""):
            self._href = attributes["href"]
            self._title_parts = []
            self._span_parts = []
        elif self._href and tag.casefold() == "h3":
            self._in_title = True
        elif self._href and tag.casefold() == "span":
            self._in_span = True
            self._current_span = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_span:
            self._current_span.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "h3" and self._in_title:
            self._in_title = False
        elif tag.casefold() == "span" and self._in_span:
            value = normalize_space(" ".join(self._current_span))
            if value:
                self._span_parts.append(value)
            self._in_span = False
        elif tag.casefold() == "a" and self._href:
            title = normalize_space(" ".join(self._title_parts))
            location = self._span_parts[0] if self._span_parts else ""
            if title:
                self.cards.append((title, location, self._href))
            self._href = ""


def _jobs_from_meta_cards(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    parser = MetaJobCardParser()
    parser.feed(text)
    return [
        Job(
            source_id=source.id,
            company=source.name,
            title=title,
            url=urljoin(base_url, href),
            location=location,
        )
        for title, location, href in parser.cards
        if _matches_title(role_filter, title, source)
        and role_filter.matches_location(location, title)
    ]


class TikTokJobCardParser(HTMLParser):
    """Extract the title and location without folding all TikTok card metadata into the title."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str]] = []
        self._href = ""
        self._in_span = False
        self._span_parts: list[str] = []
        self._current_span: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        href = attributes.get("href", "")
        if tag.casefold() == "a" and re.search(r"/search/\d{6,}/?$", href):
            self._href = href
            self._span_parts = []
        elif self._href and tag.casefold() == "span":
            self._in_span = True
            self._current_span = []

    def handle_data(self, data: str) -> None:
        if self._in_span:
            self._current_span.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "span" and self._in_span:
            value = normalize_space(" ".join(self._current_span))
            if value:
                self._span_parts.append(value)
            self._in_span = False
        elif tag.casefold() == "a" and self._href:
            if self._span_parts:
                title = self._span_parts[0]
                location = self._span_parts[1] if len(self._span_parts) > 1 else ""
                self.cards.append((title, location, self._href))
            self._href = ""


def _jobs_from_tiktok_cards(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    parser = TikTokJobCardParser()
    parser.feed(text)
    return [
        Job(
            source_id=source.id,
            company=source.name,
            title=title,
            url=urljoin(base_url, href),
            location=location,
        )
        for title, location, href in parser.cards
        if _matches_title(role_filter, title, source)
        and role_filter.matches_location(location, title)
    ]


class WalmartJobCardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, tuple[str, ...]]] = []
        self._depth = 0
        self._identifier = ""
        self._in_title = False
        self._in_span = False
        self._title_parts: list[str] = []
        self._span_values: list[str] = []
        self._current_span: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        if (
            not self._depth
            and tag.casefold() == "div"
            and attributes.get("data-testid") == "job-card"
        ):
            self._depth = 1
            self._identifier = attributes.get("data-job-id", "")
            self._title_parts = []
            self._span_values = []
            return
        if not self._depth:
            return
        if tag.casefold() == "div":
            self._depth += 1
        elif tag.casefold() == "span":
            self._in_span = True
            self._current_span = []
            if attributes.get("data-testid") == "job-title":
                self._in_title = True

    def handle_data(self, data: str) -> None:
        if self._in_span:
            self._current_span.append(data)
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if not self._depth:
            return
        if tag.casefold() == "span" and self._in_span:
            value = normalize_space(" ".join(self._current_span))
            if value:
                self._span_values.append(value)
            self._in_span = False
            self._in_title = False
        elif tag.casefold() == "div":
            self._depth -= 1
            if self._depth == 0 and self._identifier and self._title_parts:
                self.cards.append(
                    (
                        self._identifier,
                        normalize_space(" ".join(self._title_parts)),
                        tuple(self._span_values),
                    )
                )


def _jobs_from_walmart_cards(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    parser = WalmartJobCardParser()
    parser.feed(text)
    jobs: list[Job] = []
    for identifier, title, spans in parser.cards:
        location = next(
            (value for value in spans if role_filter.matches_location(value, title)),
            "",
        )
        if not _matches_title(role_filter, title, source) or not location:
            continue
        jobs.append(
            Job(
                source_id=source.id,
                company=source.name,
                title=title,
                url=f"{base_url}#{identifier}",
                location=location,
            )
        )
    return jobs


def _jobs_from_google_init_data(
    text: str,
    source: Source,
    role_filter: RoleFilter,
) -> list[Job]:
    rows = _google_result_rows(text)
    if rows is None:
        return []
    jobs: list[Job] = []
    for row in rows:
        if not isinstance(row, list) or len(row) <= 9:
            continue
        identifier = normalize_space(str(row[0]))
        title = normalize_space(row[1]) if isinstance(row[1], str) else ""
        raw_locations = row[9]
        locations: list[str] = []
        if isinstance(raw_locations, list):
            for raw_location in raw_locations:
                if (
                    isinstance(raw_location, list)
                    and raw_location
                    and isinstance(raw_location[0], str)
                ):
                    location = normalize_space(raw_location[0])
                    if location:
                        locations.append(location)
        location_text = "; ".join(dict.fromkeys(locations))[:300]
        if not identifier.isdigit() or not _matches_title(role_filter, title, source):
            continue
        if not role_filter.matches_location(location_text, title):
            continue
        jobs.append(
            Job(
                source_id=source.id,
                company=source.name,
                title=title,
                url=(
                    "https://www.google.com/about/careers/applications/jobs/results/"
                    f"{identifier}"
                ),
                location=location_text,
            )
        )
    return jobs


class EAJobCardParser(HTMLParser):
    """Extract title and location from Electronic Arts' Avature result cards."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.cards: list[tuple[str, str, str]] = []
        self._in_card = False
        self._in_title = False
        self._in_location = False
        self._href = ""
        self._title_parts: list[str] = []
        self._location_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.casefold(): value or "" for key, value in attrs}
        classes = attributes.get("class", "").split()
        if tag.casefold() == "article" and "article--result" in classes:
            self._in_card = True
            self._href = ""
            self._title_parts = []
            self._location_parts = []
        elif (
            self._in_card
            and tag.casefold() == "a"
            and "link_result" in classes
            and "/jobdetail/" in attributes.get("href", "").casefold()
        ):
            self._href = attributes["href"]
            self._in_title = True
        elif self._in_card and tag.casefold() == "span" and "list-item-location" in classes:
            self._in_location = True

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        if self._in_location:
            self._location_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "a" and self._in_title:
            self._in_title = False
        elif tag.casefold() == "span" and self._in_location:
            self._in_location = False
        elif tag.casefold() == "article" and self._in_card:
            title = normalize_space(" ".join(self._title_parts))
            location = normalize_space(" ".join(self._location_parts))
            if self._href and title:
                self.cards.append((title, location, self._href))
            self._in_card = False


def _jobs_from_ea_cards(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    parser = EAJobCardParser()
    parser.feed(text)
    return [
        Job(
            source_id=source.id,
            company=source.name,
            title=title,
            url=urljoin(base_url, href),
            location=location,
        )
        for title, location, href in parser.cards
        if _matches_title(role_filter, title, source)
        and role_filter.matches_location(location, title)
    ]


SHOPIFY_ROUTER_CHUNK = re.compile(
    r'window\.__reactRouterContext\.streamController\.enqueue\(("(?:\\.|[^"\\])*")\);'
)


def _hydrate_devalue(payload: Any) -> Any:
    """Hydrate the indexed devalue representation used by Shopify's Remix app."""
    if not isinstance(payload, list):
        return None
    memo: dict[int, Any] = {}

    def hydrate_reference(value: Any) -> Any:
        if isinstance(value, bool) or not isinstance(value, int):
            return value
        if value < 0 or value >= len(payload):
            return None
        return hydrate_index(value)

    def hydrate_index(index: int) -> Any:
        if index in memo:
            return memo[index]
        raw = payload[index]
        if isinstance(raw, list):
            result: list[Any] = []
            memo[index] = result
            result.extend(hydrate_reference(item) for item in raw)
            return result
        if isinstance(raw, dict):
            result_dict: dict[str, Any] = {}
            memo[index] = result_dict
            for raw_key, raw_value in raw.items():
                key = raw_key
                key_match = re.fullmatch(r"_(\d+)", raw_key)
                if key_match:
                    hydrated_key = hydrate_index(int(key_match.group(1)))
                    if not isinstance(hydrated_key, str):
                        continue
                    key = hydrated_key
                result_dict[key] = hydrate_reference(raw_value)
            return result_dict
        memo[index] = raw
        return raw

    return hydrate_index(0) if payload else None


def _jobs_from_shopify_router(
    text: str,
    source: Source,
    base_url: str,
    role_filter: RoleFilter,
) -> list[Job]:
    chunks: list[str] = []
    for match in SHOPIFY_ROUTER_CHUNK.finditer(text):
        try:
            chunks.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    if not chunks:
        return []
    try:
        root = _hydrate_devalue(json.loads("".join(chunks)))
    except json.JSONDecodeError:
        return []
    if not isinstance(root, dict):
        return []
    loader_data = root.get("loaderData")
    if not isinstance(loader_data, dict):
        return []
    careers = loader_data.get("($locale)/careers")
    if not isinstance(careers, dict):
        return []
    rows = careers.get("jobPostingsWithJobs")
    if not isinstance(rows, list):
        return []

    jobs: list[Job] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("jobPosting"), dict):
            continue
        posting = row["jobPosting"]
        title = _first_string(posting, TITLE_KEYS)
        location = _first_string(posting, ("locationName", "locationExternalName"))
        raw_url = _first_string(posting, ("externalLink", "applyLink"))
        if not title or not raw_url:
            continue
        if not _matches_title(role_filter, title, source) or not role_filter.matches_location(
            location, title
        ):
            continue
        jobs.append(
            Job(
                source_id=source.id,
                company=source.name,
                title=title,
                url=urljoin(base_url, raw_url),
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
        jobs.extend(_jobs_from_markdown(text, source, role_filter))
        if "workatastartup.com" in base_url:
            jobs.extend(_jobs_from_yc_cards(text, source, base_url, role_filter))
        if "metacareers.com" in base_url:
            jobs.extend(_jobs_from_meta_cards(text, source, base_url, role_filter))
        if "lifeattiktok.com" in base_url:
            jobs.extend(_jobs_from_tiktok_cards(text, source, base_url, role_filter))
        if "careers.walmart.com" in base_url:
            jobs.extend(_jobs_from_walmart_cards(text, source, base_url, role_filter))
        if "google.com/about/careers/applications/jobs/results" in base_url:
            jobs.extend(_jobs_from_google_init_data(text, source, role_filter))
        if "jobs.ea.com" in base_url:
            jobs.extend(_jobs_from_ea_cards(text, source, base_url, role_filter))
        if "shopify.com/careers" in base_url:
            jobs.extend(_jobs_from_shopify_router(text, source, base_url, role_filter))
        if "linkedin.com/jobs-guest/" in base_url:
            jobs.extend(_jobs_from_linkedin_cards(text, source, base_url, role_filter))
        parser = CareerHTMLParser()
        parser.feed(text)
        for href, label in parser.anchors:
            if "metacareers.com" in base_url and "/profile/job_details/" in href:
                continue
            if "jobs.ea.com" in base_url and "/jobdetail/" in href.casefold():
                continue
            if "lifeattiktok.com" in base_url and NUMERIC_SEARCH_HREF.search(href):
                continue
            if "linkedin.com/jobs-guest/" in base_url and "/jobs/view/" in href:
                continue
            title = label
            location = ""
            if "apply.careers.microsoft.com" in base_url and "/careers/job/" in href:
                microsoft_match = MICROSOFT_RENDERED_JOB.match(label)
                if microsoft_match:
                    title = normalize_space(microsoft_match.group("title"))
                    location = normalize_space(microsoft_match.group("location"))
            if _matches_title(role_filter, title, source) and role_filter.matches_location(
                location, title
            ):
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

        ashby_state = _json_object_after(text, "window.__appData =")
        if ashby_state is not None:
            jobs.extend(_jobs_from_json(ashby_state, source, base_url, role_filter))

    unique: dict[str, Job] = {}
    for job in jobs:
        unique[job.fingerprint] = job
    return tuple(unique.values())
