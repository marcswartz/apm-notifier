from __future__ import annotations

from html import unescape
import re

from .models import normalize_space


EXPLICIT_EARLY_CAREER = re.compile(
    r"\b(?:associate\s+product\s+manager|rotational\s+product\s+manager|"
    r"product\s+manager\s*,?\s+associate)\b",
    re.IGNORECASE,
)
GRADUATE_PRODUCT_MANAGER = re.compile(
    r"(?:\bproduct\s+manager\b.{0,100}\bgraduate\b|"
    r"\bgraduate\b.{0,100}\bproduct\s+manager\b)",
    re.IGNORECASE,
)
PRODUCT_ROLE = re.compile(
    r"\b(?:product\s+management|product\s+manager|technical\s+product\s+manager|"
    r"growth\s+product\s+manager|product\s+marketing(?:\s+manager)?)\b",
    re.IGNORECASE,
)
MARKETING_ROLE = re.compile(r"\bmarketing\b", re.IGNORECASE)
ENTRY_LEVEL_MARKETING = re.compile(
    r"(?:\b(?:associate|specialist|coordinator|graduate)\b(?:\W+\w+){0,3}\W+marketing\b|"
    r"\bmarketing\b(?:\W+\w+){0,3}\W+(?:associate|specialist|coordinator|graduate)\b)",
    re.IGNORECASE,
)
INTERNSHIP = re.compile(r"\b(?:intern(?:ship)?|co[ -]?op)\b", re.IGNORECASE)
PRODUCT_DEVELOPMENT_PROGRAM = re.compile(
    r"\bproduct\s+development\s+internship\s+program\b",
    re.IGNORECASE,
)
NEGATIVE_SENIORITY = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|head|vice president|vp)\b",
    re.IGNORECASE,
)
NON_SUMMER_TERM = re.compile(r"\b(?:fall|autumn|winter|spring)\b", re.IGNORECASE)
SUMMER_TERM = re.compile(r"\bsummer\b", re.IGNORECASE)
MASTERS_REQUIRED = re.compile(
    r"\b(?:completing|completed|pursuing|hold(?:ing)?|have)\b.{0,100}"
    r"\bmaster(?:'s|s)?\s+degree\b|"
    r"\bmaster(?:'s|s)?\s+degree\b.{0,80}\b(?:required|minimum|must)\b",
    re.IGNORECASE | re.DOTALL,
)
BACHELORS_ALLOWED = re.compile(
    r"\b(?:bachelor(?:'s|s)?\s+degree|undergraduate|bachelor\s*/\s*master|bs\s*/\s*ms)\b",
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
US_STATE_ABBREVIATION = re.compile(
    r",\s*(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|"
    r"MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY)"
    r"(?![A-Za-z])",
    re.IGNORECASE,
)


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

    def matches(self, title: str, include_adjacent_marketing: bool = False) -> bool:
        candidate = normalize_space(title)
        if len(candidate) < 5 or len(candidate) > 220:
            return False

        years = {int(value) for value in re.findall(r"\b20\d{2}\b", candidate)}
        if years & self.excluded_years and self.target_year not in years:
            return False
        if NON_SUMMER_TERM.search(candidate) and not SUMMER_TERM.search(candidate):
            return False

        early_career = bool(
            EXPLICIT_EARLY_CAREER.search(candidate) or GRADUATE_PRODUCT_MANAGER.search(candidate)
        )
        internship = bool(INTERNSHIP.search(candidate) and PRODUCT_ROLE.search(candidate))
        adjacent_marketing = bool(
            include_adjacent_marketing
            and (
                (INTERNSHIP.search(candidate) and MARKETING_ROLE.search(candidate))
                or ENTRY_LEVEL_MARKETING.search(candidate)
            )
        )
        product_development_program = bool(PRODUCT_DEVELOPMENT_PROGRAM.search(candidate))
        if (
            not early_career
            and not internship
            and not adjacent_marketing
            and not product_development_program
        ):
            return False

        if NEGATIVE_SENIORITY.search(candidate) and not INTERNSHIP.search(candidate):
            return False
        return True

    @staticmethod
    def is_graduate_product_manager(title: str) -> bool:
        return bool(GRADUATE_PRODUCT_MANAGER.search(normalize_space(title)))

    @staticmethod
    def allows_bachelors(detail_text: str) -> bool:
        """Reject roles whose minimum qualifications explicitly require a master's degree."""
        readable = unescape(detail_text).replace("\\n", "\n").replace("\\'", "'")
        lowered = readable.casefold()
        start = lowered.find("minimum qualifications")
        if start >= 0:
            readable = readable[start : start + 8_000]
            preferred = readable.casefold().find("preferred qualifications")
            if preferred >= 0:
                readable = readable[:preferred]
        return not MASTERS_REQUIRED.search(readable) or bool(BACHELORS_ALLOWED.search(readable))

    def matches_location(self, location: str, title: str = "") -> bool:
        """Accept only roles with positive evidence of an allowed country."""
        location_candidate = normalize_space(location)
        title_candidate = normalize_space(title)
        searchable = " | ".join(value for value in (location_candidate, title_candidate) if value)
        for country in self.allowed_countries:
            if country == "US" and US_STATE_ABBREVIATION.search(location_candidate):
                return True
            if LOCATION_PATTERNS[country].search(searchable):
                return True
            for code in COUNTRY_CODES[country]:
                code_pattern = rf"(?<![A-Za-z]){re.escape(code)}(?![A-Za-z])"
                if re.search(code_pattern, location_candidate, re.IGNORECASE):
                    return True
                if re.search(code_pattern, title_candidate):
                    return True
        return False
