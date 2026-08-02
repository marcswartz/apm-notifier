from __future__ import annotations

import re

from .models import normalize_space


EXPLICIT_EARLY_CAREER = re.compile(
    r"\b(?:associate\s+product\s+manager|rotational\s+product\s+manager|"
    r"product\s+manager\s*,?\s+associate)\b",
    re.IGNORECASE,
)
PRODUCT_ROLE = re.compile(
    r"\b(?:product\s+management|product\s+manager|technical\s+product\s+manager|"
    r"growth\s+product\s+manager|product\s+marketing(?:\s+manager)?)\b",
    re.IGNORECASE,
)
INTERNSHIP = re.compile(r"\b(?:intern(?:ship)?|co[ -]?op)\b", re.IGNORECASE)
NEGATIVE_SENIORITY = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|head|vice president|vp)\b",
    re.IGNORECASE,
)

SUPPORTED_COUNTRIES = frozenset({"US", "CA", "UK"})
COUNTRY_CODES = {
    "US": ("US", "USA"),
    "CA": ("CA", "CAN"),
    "UK": ("UK", "GB", "GBR"),
}
LOCATION_TERMS = {
    "US": (
        "united states",
        "united states of america",
        "alabama",
        "alaska",
        "arizona",
        "arkansas",
        "california",
        "colorado",
        "connecticut",
        "delaware",
        "district of columbia",
        "florida",
        "hawaii",
        "idaho",
        "illinois",
        "indiana",
        "iowa",
        "kansas",
        "kentucky",
        "louisiana",
        "maine",
        "maryland",
        "massachusetts",
        "michigan",
        "minnesota",
        "mississippi",
        "missouri",
        "montana",
        "nebraska",
        "nevada",
        "new hampshire",
        "new jersey",
        "new mexico",
        "new york",
        "north carolina",
        "north dakota",
        "ohio",
        "oklahoma",
        "oregon",
        "pennsylvania",
        "rhode island",
        "south carolina",
        "south dakota",
        "tennessee",
        "texas",
        "utah",
        "vermont",
        "virginia",
        "washington state",
        "west virginia",
        "wisconsin",
        "wyoming",
        "atlanta",
        "austin",
        "bellevue",
        "boston",
        "boulder",
        "brooklyn",
        "chicago",
        "cupertino",
        "dallas",
        "denver",
        "detroit",
        "houston",
        "irvine",
        "los angeles",
        "menlo park",
        "miami",
        "mountain view",
        "nashville",
        "new york city",
        "palo alto",
        "pittsburgh",
        "raleigh",
        "redmond",
        "san diego",
        "san francisco",
        "san jose",
        "seattle",
        "sunnyvale",
        "washington dc",
        "washington, dc",
    ),
    "CA": (
        "canada",
        "alberta",
        "british columbia",
        "manitoba",
        "new brunswick",
        "newfoundland and labrador",
        "northwest territories",
        "nova scotia",
        "nunavut",
        "ontario",
        "prince edward island",
        "quebec",
        "québec",
        "saskatchewan",
        "yukon",
        "burnaby",
        "calgary",
        "edmonton",
        "kitchener",
        "markham",
        "mississauga",
        "montreal",
        "montréal",
        "ottawa",
        "toronto",
        "vancouver",
        "waterloo",
    ),
    "UK": (
        "united kingdom",
        "great britain",
        "england",
        "scotland",
        "wales",
        "northern ireland",
        "belfast",
        "birmingham",
        "bristol",
        "edinburgh",
        "glasgow",
        "leeds",
        "liverpool",
        "london",
        "manchester",
        "oxford",
        "reading",
    ),
}


def _term_pattern(terms: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(term) for term in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<![a-z])(?:{alternatives})(?![a-z])", re.IGNORECASE)


LOCATION_PATTERNS = {country: _term_pattern(terms) for country, terms in LOCATION_TERMS.items()}


class RoleFilter:
    def __init__(
        self,
        target_year: int,
        excluded_years: tuple[int, ...],
        allowed_countries: tuple[str, ...] = ("US", "CA", "UK"),
    ) -> None:
        self.target_year = target_year
        self.excluded_years = set(excluded_years)
        self.allowed_countries = tuple(dict.fromkeys(country.strip().upper() for country in allowed_countries))
        unsupported = set(self.allowed_countries) - SUPPORTED_COUNTRIES
        if unsupported:
            raise ValueError(f"Unsupported ALLOWED_COUNTRIES value(s): {', '.join(sorted(unsupported))}")
        if not self.allowed_countries:
            raise ValueError("ALLOWED_COUNTRIES must contain at least one country")

    def matches(self, title: str) -> bool:
        candidate = normalize_space(title)
        if len(candidate) < 5 or len(candidate) > 220:
            return False

        years = {int(value) for value in re.findall(r"\b20\d{2}\b", candidate)}
        if years & self.excluded_years and self.target_year not in years:
            return False

        early_career = bool(EXPLICIT_EARLY_CAREER.search(candidate))
        internship = bool(INTERNSHIP.search(candidate) and PRODUCT_ROLE.search(candidate))
        if not early_career and not internship:
            return False

        if NEGATIVE_SENIORITY.search(candidate) and not INTERNSHIP.search(candidate):
            return False
        return True

    def matches_location(self, location: str, title: str = "") -> bool:
        """Accept only roles with positive evidence of an allowed country."""
        location_candidate = normalize_space(location)
        title_candidate = normalize_space(title)
        searchable = " | ".join(value for value in (location_candidate, title_candidate) if value)
        for country in self.allowed_countries:
            if LOCATION_PATTERNS[country].search(searchable):
                return True
            for code in COUNTRY_CODES[country]:
                code_pattern = rf"(?<![A-Za-z]){re.escape(code)}(?![A-Za-z])"
                if re.search(code_pattern, location_candidate, re.IGNORECASE):
                    return True
                if re.search(code_pattern, title_candidate):
                    return True
        return False
