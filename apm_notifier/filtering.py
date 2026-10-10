from __future__ import annotations

from html import unescape
import re

from .models import normalize_space


EXPLICIT_EARLY_CAREER = re.compile(
    r"(?:\b(?:associate|rotational|apprentice|apprenticeship|junior|trainee|"
    r"entry[ -]level|early[ -]career)\b.{0,100}\bproduct\s+(?:manager|management|owner|builder)\b|"
    r"\bproduct\s+(?:manager|management|owner|builder)\b.{0,100}\b(?:associate|rotational|"
    r"apprentice|apprenticeship|junior|trainee|entry[ -]level|early[ -]career)\b|"
    r"\bproduct\s+(?:manager|owner)\s+I\b)",
    re.IGNORECASE,
)
GRADUATE_MARKER = re.compile(
    r"\b(?:graduates?|new[ -]grads?|new[ -]college[ -]grads?)\b",
    re.IGNORECASE,
)
EARLY_CAREER_MARKER = re.compile(
    r"\b(?:associate|rotational|apprentice|apprenticeship|junior|trainee|"
    r"entry[ -]level|early[ -]career)\b",
    re.IGNORECASE,
)
PRODUCT_ROLE = re.compile(
    r"\b(?:product\s+management|product\s+manager|technical\s+product\s+manager|"
    r"growth\s+product\s+manager|product\s+owner|product\s+builder|product\s+marketing(?:\s+manager)?|"
    r"product\s+(?:strategy|solutions?|operations?|growth))\b",
    re.IGNORECASE,
)
PRODUCT_SPECIALIST = re.compile(
    r"(?:\b(?:specialist|analyst|coordinator)\b(?:\W+\w+){0,3}\W+product\s+(?:management|manager)\b|"
    r"\bproduct\s+(?:management|manager)\b(?:\W+\w+){0,3}\W+(?:specialist|analyst|coordinator)\b|"
    r"\bproduct\s+(?:specialist|analyst|coordinator)\b)",
    re.IGNORECASE,
)
GROWTH_PRODUCT_MANAGER = re.compile(
    r"(?:\bgrowth\b.{0,60}\bproduct\s+manager\b|"
    r"\bproduct\s+manager\b.{0,60}\bgrowth\b)",
    re.IGNORECASE,
)
MARKETING_ROLE = re.compile(r"\b(?:marketing|campaigns?|advertising|ads|growth)\b", re.IGNORECASE)
GRADUATE_ACCOUNT_ROLE = re.compile(r"\baccount\s+(?:manager|management|strategist)\b", re.IGNORECASE)
ENTRY_LEVEL_MARKETING = re.compile(
    r"(?:\b(?:associate|analyst|specialist|coordinator|graduate)\b(?:\W+\w+){0,3}\W+marketing\b|"
    r"\bmarketing\b(?:\W+\w+){0,3}\W+(?:associate|analyst|specialist|coordinator|graduate)\b)",
    re.IGNORECASE,
)
NON_ENTRY_ADJACENT_MARKETING = re.compile(
    r"\bassociate\s+manager\b|\bmanaging\s+consultant\b|\b(?:sourcing|procurement)\b",
    re.IGNORECASE,
)
UNRELATED_JOB_FUNCTION = re.compile(
    r"\b(?:engineer|developer|designer|scientist)\b|"
    r"\b(?:engineering|design)\s+(?:(?:project|program)\s+)?(?:intern(?:ship)?|graduates?)\b",
    re.IGNORECASE,
)
INTERNSHIP = re.compile(r"\b(?:intern(?:ship)?|co[ -]?op)\b", re.IGNORECASE)
PRODUCT_DEVELOPMENT_PROGRAM = re.compile(
    r"\bproduct\s+development\s+internship\s+program\b",
    re.IGNORECASE,
)
NEGATIVE_SENIORITY = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|director|head|lead|vice president|vp)\b",
    re.IGNORECASE,
)
NON_SUMMER_TERM = re.compile(r"\b(?:fall|autumn|winter|spring)\b", re.IGNORECASE)
SUMMER_TERM = re.compile(r"\bsummer\b", re.IGNORECASE)
ADVANCED_DEGREE = re.compile(
    r"\b(?:master(?:'s|s)(?:\s+degree)?|master\s+(?:degree|of\s+\w+)|mba|m\.?\s?sc\.?|"
    r"m\.?\s?s\b(?!\.?\s+(?:office|excel|word|powerpoint|outlook|teams|access|project|"
    r"sql|windows|azure|dynamics|power\s*bi)\b)\.?|"
    r"ph\.?\s?d\.?|doctorate|doctoral\s+degree)\b",
    re.IGNORECASE,
)
BACHELORS_ALLOWED = re.compile(
    r"\b(?:bachelor(?:'s|s)?|undergraduate|b\.?\s?s\.?|b\.?\s?a\.?|b\.?\s?sc\.?)\b",
    re.IGNORECASE,
)
EDUCATION_REQUIRED = re.compile(
    r"\b(?:completing|completed|pursuing|enrolled|hold(?:ing)?|have|must|required?|minimum|essential)\b",
    re.IGNORECASE,
)
EDUCATION_PREFERRED = re.compile(
    r"\b(?:preferred|desirable|optional|nice\s+to\s+have|a\s+plus)\b", re.IGNORECASE
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

    def matches(
        self,
        title: str,
        include_adjacent_marketing: bool = False,
        include_growth_product_roles: bool = False,
        include_product_specialists: bool = True,
    ) -> bool:
        candidate = re.sub(r"[\u2010-\u2015]", "-", normalize_space(title))
        if len(candidate) < 5 or len(candidate) > 220:
            return False

        years = {int(value) for value in re.findall(r"\b20\d{2}\b", candidate)}
        if years & self.excluded_years and self.target_year not in years:
            return False
        if UNRELATED_JOB_FUNCTION.search(candidate):
            return False
        graduate = bool(GRADUATE_MARKER.search(candidate))
        early_career = bool(
            EXPLICIT_EARLY_CAREER.search(candidate)
            or (
                PRODUCT_ROLE.search(candidate)
                and (
                    graduate
                    or (
                        EARLY_CAREER_MARKER.search(candidate)
                        and not NON_ENTRY_ADJACENT_MARKETING.search(candidate)
                    )
                )
            )
        )
        internship = bool(INTERNSHIP.search(candidate) and PRODUCT_ROLE.search(candidate))
        # Seasonal limits apply to internships, not full-time graduate cohorts.
        if INTERNSHIP.search(candidate) and NON_SUMMER_TERM.search(candidate) and not SUMMER_TERM.search(candidate):
            return False
        adjacent_marketing = bool(
            include_adjacent_marketing
            and not NON_ENTRY_ADJACENT_MARKETING.search(candidate)
            and (
                (INTERNSHIP.search(candidate) and MARKETING_ROLE.search(candidate))
                or ENTRY_LEVEL_MARKETING.search(candidate)
                or (
                    MARKETING_ROLE.search(candidate)
                    and (graduate or EARLY_CAREER_MARKER.search(candidate))
                )
                or (graduate and GRADUATE_ACCOUNT_ROLE.search(candidate))
            )
        )
        product_development_program = bool(PRODUCT_DEVELOPMENT_PROGRAM.search(candidate))
        growth_product_role = bool(
            include_growth_product_roles and GROWTH_PRODUCT_MANAGER.search(candidate)
        )
        product_specialist = bool(include_product_specialists and PRODUCT_SPECIALIST.search(candidate))
        if (
            not early_career
            and not internship
            and not adjacent_marketing
            and not product_development_program
            and not growth_product_role
            and not product_specialist
        ):
            return False

        if NEGATIVE_SENIORITY.search(candidate) and not INTERNSHIP.search(candidate):
            return False
        return True

    @staticmethod
    def is_graduate_product_manager(title: str) -> bool:
        candidate = re.sub(r"[\u2010-\u2015]", "-", normalize_space(title))
        return bool(GRADUATE_MARKER.search(candidate) and PRODUCT_ROLE.search(candidate))

    @staticmethod
    def is_graduate_role(title: str) -> bool:
        candidate = re.sub(r"[\u2010-\u2015]", "-", normalize_space(title))
        return bool(GRADUATE_MARKER.search(candidate) or ADVANCED_DEGREE.search(candidate))

    @staticmethod
    def allows_bachelors(detail_text: str, title: str = "") -> bool:
        """Reject explicit postgraduate minimums while preserving bachelor alternatives."""
        readable = unescape(detail_text).replace("\\n", "\n").replace("\\'", "'")
        readable = readable.translate(str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'"}))
        normalized_title = title.translate(str.maketrans({"\u2019": "'", "\u2018": "'"}))
        if (
            ADVANCED_DEGREE.search(normalized_title)
            and not BACHELORS_ALLOWED.search(normalized_title)
            and not EDUCATION_PREFERRED.search(normalized_title)
        ):
            return False

        # Keep list items and paragraphs separate so an unrelated bachelor's mention
        # cannot override a later mandatory MBA/PhD qualification.
        readable = re.sub(r"<\s*(?:br\b[^>]*|/?(?:li|p|div|h[1-6])\b[^>]*)>", "\n\n", readable, flags=re.IGNORECASE)
        readable = re.sub(r"<[^>]+>", " ", readable)
        readable = re.sub(r"\n\s*[-*\u2022]\s*", "\n\n", readable)
        readable = re.sub(r"(?<!\n)\n(?!\n)", " ", readable)
        start = re.search(r"\b(?:minimum|basic|required)\s+qualifications\b|\brequirements\b", readable, re.IGNORECASE)
        within_minimums = start is not None
        if start:
            readable = readable[start.end() : start.end() + 8_000]
        preferred = re.search(r"\bpreferred\s+qualifications\b|\bnice\s+to\s+have\b", readable, re.IGNORECASE)
        if preferred:
            readable = readable[: preferred.start()]
        # Avoid treating abbreviation dots as sentence endings.
        readable = re.sub(r"\b([BMP])\.\s*([ASHD])\.", r"\1\2", readable, flags=re.IGNORECASE)
        readable = re.sub(r"\bPh\.\s?D\.", "PhD", readable, flags=re.IGNORECASE)
        for clause in re.split(r"\n\s*\n|[;.!?]\s+", readable):
            if not within_minimums and not EDUCATION_REQUIRED.search(clause):
                continue
            advanced_degrees = list(ADVANCED_DEGREE.finditer(clause))
            for advanced_index, advanced in enumerate(advanced_degrees):
                next_degree = advanced_degrees[advanced_index + 1].start() if advanced_index + 1 < len(advanced_degrees) else len(clause)
                degree_context = clause[advanced.start() : next_degree]
                if EDUCATION_PREFERRED.search(degree_context):
                    continue
                bachelor = BACHELORS_ALLOWED.search(clause)
                if bachelor:
                    between = clause[min(bachelor.end(), advanced.end()) : max(bachelor.start(), advanced.start())]
                    # BS/MS and bachelor's or master's qualify; bachelor's AND MBA does not.
                    if re.search(r"\bor\b|/", between, re.IGNORECASE) and not re.search(r"\band\b", between, re.IGNORECASE):
                        continue
                return False
        return True

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
