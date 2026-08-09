"""Find the current URL for a visa authority when the stored one dies.

The problem this solves is concrete: `aps-egypt.de` and `ambcairo.esteri.it` are
NXDOMAIN, so those rows in `visa_sources` are dead forever and the ingestion run
reports two failures every time. Consular URLs move; a hardcoded link is a
liability with a timer on it.

**Search is used for discovery, never for authority.**

The tempting version of this is "search the web for Egyptian student visa
requirements and extract the top result". That fails in the one way that matters
here: not by returning nothing, but by returning something confidently wrong. An
immigration consultancy's blog, a forum answer, or a 2019 archived page all
extract cleanly into the schema and look exactly like a real answer. A student
then books an appointment against a financial-proof figure that changed two
years ago.

So the authority list stays curated. `visa_sources` already names an issuing
body -- APS Cairo, IND, the German Embassy -- and this module only answers
"where does that body live now", filtered to an allowlist of official domains.
A result off the allowlist is discarded rather than ranked lower, so extraction
never sees an unofficial page.

**Nationality is part of the query, not a detail.**

Visa requirements are per applicant nationality. The financial proof, the
appointment route and the document list for an Egyptian applying to Germany are
not the ones a Brazilian gets, and a generic national portal will happily
describe the wrong one. Every query is scoped to Egyptian applicants and the
consular mission serving Egypt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)


# Domains an extraction may be run against.
#
# Suffix matched, so `cairo.diplo.de` passes on `.diplo.de`. Deliberately narrow:
# an allowlist that grows to "anything plausible" is not an allowlist. Adding an
# entry should be a reviewed decision, because it widens what the system will
# treat as authoritative.
OFFICIAL_DOMAIN_SUFFIXES: tuple[str, ...] = (
    # Government and consular
    ".gov.uk",
    ".diplo.de",          # German missions
    ".esteri.it",         # Italian missions
    ".gob.es",            # Spanish government
    ".gouv.fr",
    ".mzv.gov.cz",
    ".government.nl",
    "ind.nl",             # Dutch immigration
    "migrationsverket.se",
    "nawa.gov.pl",
    ".europa.eu",
    ".admin.ch",
    ".gv.at",
    ".belgium.be",
    ".ie",                # Irish government uses irishimmigration.ie / dfa.ie
    # Official study/mobility bodies
    "campusfrance.org",
    "daad.de",
    "studyinpoland.pl",
    "stipendiumhungaricum.hu",
    # Official outsourced visa handling. Included because several missions route
    # applications exclusively through them, so they ARE the procedural
    # authority even though they are commercial.
    "vfsglobal.com",
    "tlscontact.com",
)

# Generic top-level government patterns, checked when no explicit suffix matches.
GOVERNMENT_PATTERNS = (
    re.compile(r"\.gov(\.[a-z]{2})?$"),
    re.compile(r"\.gouv\.[a-z]{2}$"),
    re.compile(r"\.gob\.[a-z]{2}$"),
    re.compile(r"\.gc\.ca$"),
)

# Hosts that look authoritative to a search engine and are not. Listed
# explicitly because several rank above the real consulate for exactly the
# queries this module runs.
BLOCKED_HOSTS = (
    "wikipedia.org",
    "reddit.com",
    "quora.com",
    "facebook.com",
    "youtube.com",
    "visaguide.world",
    "ivisa.com",
    "visahq.com",
    "schengenvisainfo.com",
)

# The applicant nationality this catalogue serves. Not a parameter with a
# default: every source in `visa_sources` is the Egyptian-applicant route, and a
# query that omits it returns the generic national page describing a different
# applicant's requirements.
APPLICANT_NATIONALITY = "Egyptian"
APPLICANT_COUNTRY = "Egypt"


# Destination country -> host fragments that belong to THAT country's authority.
#
# Added after the first live run resolved "APS Cairo" (German academic
# evaluation, Germany) to eg.usembassy.gov -- the US embassy in Cairo. An
# official government domain, in the right city, for entirely the wrong country.
# The allowlist answered "is this a government site" when the question is "is
# this the DESTINATION country's authority", and a generic .gov pattern cannot
# tell those apart.
#
# A candidate must now match its destination country as well as being official.
COUNTRY_HOST_HINTS: dict[str, tuple[str, ...]] = {
    "germany": (".de", "diplo.de", "daad.de", "/deu/", "/germany/"),
    "italy": (".it", "esteri.it", "/ita/", "/italy/"),
    "spain": (".es", "exteriores.gob.es", "/esp/", "/spain/"),
    "france": (".fr", "campusfrance.org", "gouv.fr", "/fra/", "/france/"),
    "netherlands": (".nl", "ind.nl", "government.nl", "/nld/", "/netherlands/"),
    "sweden": (".se", "migrationsverket.se", "/swe/", "/sweden/"),
    "poland": (".pl", "nawa.gov.pl", "/pol/", "/poland/"),
    "czech republic": (".cz", "mzv.gov.cz", "/cze/", "/czech"),
    "hungary": (".hu", "stipendiumhungaricum.hu", "/hun/", "/hungary/"),
    "united kingdom": (".uk", "gov.uk", "/gbr/", "/uk/"),
    "ireland": (".ie", "/irl/", "/ireland/"),
    "austria": (".at", "gv.at", "/aut/", "/austria/"),
    "switzerland": (".ch", "admin.ch", "/che/", "/switzerland/"),
    "belgium": (".be", "belgium.be", "/bel/", "/belgium/"),
}


def belongs_to_destination(url: str, country: str) -> bool:
    """Whether this URL is the DESTINATION country's authority.

    Applied on top of is_official, never instead of it. Both questions have to
    be answered: a consultancy blog on a .de domain fails the first, and the US
    embassy in Cairo fails the second.

    An unmapped country returns False rather than True. Failing open here would
    reinstate exactly the defect this function exists to close, and a missing
    map entry is a five-line fix that someone will notice because discovery
    stops finding anything for that country.
    """
    hints = COUNTRY_HOST_HINTS.get(country.strip().lower())
    if not hints:
        return False

    lowered = url.lower()
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False

    for hint in hints:
        if hint.startswith("/"):
            # A path fragment: VFS and TLS serve every country from one host,
            # so the country lives in the path rather than the domain.
            if hint in lowered:
                return True
        elif host.endswith(hint) or hint in host:
            return True
    return False


@dataclass(frozen=True)
class Candidate:
    url: str
    title: str
    snippet: str
    host: str


def is_official(url: str) -> bool:
    """Whether this URL may be treated as an authority."""
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False

    if any(blocked in host for blocked in BLOCKED_HOSTS):
        return False

    if any(host == suffix or host.endswith(suffix) for suffix in OFFICIAL_DOMAIN_SUFFIXES):
        return True

    return any(pattern.search(host) for pattern in GOVERNMENT_PATTERNS)


def build_queries(country: str, visa_type: str, issuing_body: str) -> list[str]:
    """Queries for one authority, most specific first.

    Every one names the issuing body AND the applicant nationality. Dropping the
    body finds some page about the visa; dropping the nationality finds the
    requirements for the wrong applicant. Both are worse than finding nothing,
    because both produce output.
    """
    return [
        f"{issuing_body} {visa_type} {APPLICANT_NATIONALITY} applicants official site",
        f"{issuing_body} {country} {visa_type} requirements {APPLICANT_COUNTRY}",
        f"{country} {visa_type} for {APPLICANT_NATIONALITY} students official embassy {APPLICANT_COUNTRY}",
    ]


def rank(candidates: list[Candidate], issuing_body: str) -> list[Candidate]:
    """Order official candidates by how well they match the named authority.

    Ranking runs AFTER the allowlist filter, never instead of it. Its only job
    is to choose among pages that are already authoritative.
    """
    body_terms = {t for t in re.split(r"\W+", issuing_body.lower()) if len(t) > 2}

    def score(candidate: Candidate) -> tuple[int, int, int]:
        haystack = f"{candidate.title} {candidate.url}".lower()
        body_hits = sum(1 for term in body_terms if term in haystack)
        # A page that names the applicant nationality is describing the right
        # route; a generic national page usually does not.
        nationality_hit = int(
            APPLICANT_NATIONALITY.lower() in haystack
            or APPLICANT_COUNTRY.lower() in haystack
        )
        # Shorter paths tend to be the landing page rather than a news item.
        depth = -len(urlparse(candidate.url).path.strip("/").split("/"))
        return (body_hits, nationality_hit, depth)

    return sorted(candidates, key=score, reverse=True)


def search(query: str, max_results: int = 10) -> list[Candidate]:
    """Run one web search.

    DuckDuckGo through `ddgs`: no API key, no account, no quota to administer.
    That matters more than result quality here because the allowlist does the
    quality work -- discovery only has to surface the official page somewhere in
    ten results, not rank it first.

    Volume is tiny by design. This runs when a stored link is dead or stale, not
    on every ingestion pass, so it is a few dozen queries a month rather than
    the thousands that would get an unofficial client blocked.
    """
    try:
        from ddgs import DDGS
    except ImportError:  # pragma: no cover - dependency is optional
        try:
            from duckduckgo_search import DDGS  # older package name
        except ImportError:
            logger.warning("visa_discovery_unavailable", reason="ddgs not installed")
            return []

    try:
        with DDGS() as client:
            raw = list(client.text(query, max_results=max_results))
    except Exception as error:
        # A search failure is not a run failure. The caller keeps the dead link
        # and reports it, which is the state we were already in.
        logger.warning("visa_discovery_search_failed", query=query, error=str(error))
        return []

    candidates: list[Candidate] = []
    for item in raw:
        url = item.get("href") or item.get("url") or ""
        if not url:
            continue
        candidates.append(
            Candidate(
                url=url,
                title=item.get("title") or "",
                snippet=item.get("body") or "",
                host=(urlparse(url).hostname or "").lower(),
            )
        )
    return candidates


def discover(country: str, visa_type: str, issuing_body: str) -> Candidate | None:
    """Find the current official URL for one authority, or None.

    None is a real answer and the caller must treat it as one. Returning a
    best-effort unofficial link would defeat the entire point of the allowlist.
    """
    seen: set[str] = set()
    official: list[Candidate] = []

    for query in build_queries(country, visa_type, issuing_body):
        for candidate in search(query):
            if candidate.url in seen:
                continue
            seen.add(candidate.url)
            if is_official(candidate.url) and belongs_to_destination(
                candidate.url, country
            ):
                official.append(candidate)

        # Stop as soon as the more specific query has produced enough to choose
        # between; the later queries are broader and only exist as fallbacks.
        if len(official) >= 3:
            break

    if not official:
        logger.warning(
            "visa_discovery_no_official_result",
            country=country,
            issuing_body=issuing_body,
            examined=len(seen),
        )
        return None

    best = rank(official, issuing_body)[0]
    logger.info(
        "visa_discovery_resolved",
        country=country,
        issuing_body=issuing_body,
        url=best.url,
        examined=len(seen),
        official_candidates=len(official),
    )
    return best
