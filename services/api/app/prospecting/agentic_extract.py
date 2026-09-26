"""C.4 — level-1 agentic extraction PoC (read-only, politeness-first).

WHAT "LEVEL 1" MEANS
    One operator-selected public page -> deterministic, provenance-carrying
    facts. No crawling, no JavaScript execution, no login, no paywall bypass,
    no LLM in the loop. Every extracted fact carries where it came from, when,
    and how confident the extractor is.

    Level 2 (browser rendering, multi-page crawl, LLM-assisted extraction) is
    deliberately NOT implemented: each of those changes the legal and
    operational posture, so they need their own decision, not a bigger PoC.

WHAT THIS MODULE MUST NEVER DO
    It computes no score, no price, no max price, no RAV, no valuation and no
    recommendation. It extracts *facts about a public page* and stops. The
    boundary is enforced in code by ``FORBIDDEN_OUTPUT_FIELDS`` and
    ``assert_no_decisional_fields()``, and locked by tests — not by convention.

POLITENESS (all enforced before a socket is opened)
    * robots.txt is fetched and ``can_fetch`` is honoured for this user agent.
    * ``Crawl-delay`` from robots.txt is honoured, capped by policy.
    * a per-host minimum interval rate-limits repeated runs in-process.
    * a declared, contactable User-Agent identifies the crawler.
    * SSRF guards are reused from ``analyzer`` (no private/loopback/metadata
      ranges, no credentials in URL, ports 80/443 only, bounded redirects).
    * bounded response size and bounded fetch time.

TERMS OF SERVICE
    Automated access is a legal question, not an engineering one, so it is not
    decidable by code. ``TOS_RESTRICTED_HOSTS`` is a **human-maintained**
    denylist: if a host is listed, we refuse before fetching. An empty list is
    not a claim that every other site permits it — it is a register that a
    human must own. See DEC-004 in docs/status/decisions-required.md.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from app.prospecting.analyzer import (
    MAX_HTML_BYTES,
    USER_AGENT,
    WebsiteAuditError,
    _bounded_fetch,
    normalize_public_url,
)

EXTRACTOR_VERSION = "agentic-extract-poc/1.0"
EXTRACTION_LEVEL = 1

# Output fields this module is forbidden to produce. If one of these ever
# appears, something has quietly turned a fact-extractor into a decision
# engine — and that is exactly the failure mode this list exists to catch.
FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {
        "score",
        "scores",
        "priority_score",
        "price",
        "prices",
        "max_price",
        "min_price",
        "recommended_price",
        "rav",
        "valuation",
        "margin",
        "budget",
        "forecast",
    }
)

#: Hosts whose terms of service prohibit automated access. Human-maintained.
#: Populate from a legal review, never from a heuristic.
TOS_RESTRICTED_HOSTS: frozenset[str] = frozenset()

#: Per-extractor confidence. These are hand-set and documented so downstream
#: consumers can show uncertainty honestly instead of implying precision.
CONFIDENCE = {
    "json_ld_organization": 0.9,
    "meta_site_name": 0.7,
    "title": 0.5,
    "mailto_link": 0.9,
    "email_regex": 0.6,
    "phone_regex": 0.6,
    "org_number_luhn": 0.85,
    "postal_code_regex": 0.5,
    "social_link": 0.8,
}


@dataclass(frozen=True)
class PolitenessPolicy:
    """Knobs for the politeness layer. Defaults are deliberately conservative."""

    min_interval_seconds: float = 2.0
    honour_crawl_delay: bool = True
    max_crawl_delay_seconds: float = 10.0
    user_agent: str = USER_AGENT
    max_bytes: int = MAX_HTML_BYTES
    timeout_seconds: int = 10
    #: Level 1 audits one page. Anything above 1 is level 2 and not supported.
    max_pages_per_run: int = 1


@dataclass
class HostRateLimiter:
    """In-process per-host throttle.

    Deliberately in-process only: a distributed limiter would need shared
    state, and this PoC must never be the thing that decides how hard we hit
    someone else's server. Production hardening is DEC-003.
    """

    min_interval: float = 2.0
    _last_seen: dict[str, float] = field(default_factory=dict)

    def seconds_to_wait(self, host: str, now: float) -> float:
        last = self._last_seen.get(host)
        if last is None:
            return 0.0
        return max(0.0, self.min_interval - (now - last))

    def mark(self, host: str, now: float) -> None:
        self._last_seen[host] = now


@dataclass(frozen=True)
class RobotsVerdict:
    allowed: bool
    crawl_delay_seconds: float | None
    source: str  # "robots.txt" | "robots.txt-absent"


@dataclass(frozen=True)
class ExtractedFact:
    field: str
    value: str
    extractor: str
    confidence: float
    evidence: str


@dataclass(frozen=True)
class ExtractionResult:
    level: int
    requested_url: str
    final_url: str
    fetched_at: str
    content_sha256: str
    facts: tuple[ExtractedFact, ...]
    politeness: dict
    limitations: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "extractor_version": EXTRACTOR_VERSION,
            "requested_url": self.requested_url,
            "final_url": self.final_url,
            "fetched_at": self.fetched_at,
            "content_sha256": self.content_sha256,
            "facts": [
                {
                    "field": fact.field,
                    "value": fact.value,
                    "extractor": fact.extractor,
                    "confidence": fact.confidence,
                    "evidence": fact.evidence,
                }
                for fact in self.facts
            ],
            "politeness": dict(self.politeness),
            "limitations": list(self.limitations),
        }


def assert_no_decisional_fields(payload: dict) -> None:
    """Fail closed if the payload grew a scoring/pricing field.

    Walks nested dicts/keys so a fact list cannot smuggle one in.
    """
    stack: list[object] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            for key, value in current.items():
                if str(key).lower() in FORBIDDEN_OUTPUT_FIELDS:
                    raise WebsiteAuditError(
                        "DECISIONAL_FIELD_BLOCKED",
                        f"'{key}' is a decisional field; this extractor produces facts only",
                        422,
                    )
                stack.append(value)
        elif isinstance(current, (list, tuple)):
            stack.extend(current)


# --------------------------------------------------------------------------- #
# Politeness
# --------------------------------------------------------------------------- #


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").strip(".").lower()


def is_tos_restricted(url: str) -> bool:
    host = host_of(url)
    if not host:
        return False
    return any(host == blocked or host.endswith(f".{blocked}") for blocked in TOS_RESTRICTED_HOSTS)


def robots_verdict(url: str, *, user_agent: str = USER_AGENT) -> RobotsVerdict:
    """Fetch robots.txt and return allow + crawl-delay.

    A missing robots.txt (HTTP error) is treated as "no declared restriction"
    — the same rule the existing website audit uses. Network/security failures
    are re-raised: we never treat a failure as permission.
    """
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        body, _, _, _ = _bounded_fetch(robots_url, accept="text/plain,*/*;q=0.2", max_bytes=256_000)
    except WebsiteAuditError as exc:
        if exc.code == "UPSTREAM_HTTP_ERROR":
            return RobotsVerdict(allowed=True, crawl_delay_seconds=None, source="robots.txt-absent")
        raise

    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(body.decode("utf-8", errors="replace").splitlines())

    allowed = parser.can_fetch(user_agent, url)
    delay: float | None = None
    try:
        raw_delay = parser.crawl_delay(user_agent)
    except Exception:
        raw_delay = None
    if raw_delay is not None:
        try:
            delay = float(raw_delay)
        except (TypeError, ValueError):
            delay = None
    return RobotsVerdict(allowed=allowed, crawl_delay_seconds=delay, source="robots.txt")


# --------------------------------------------------------------------------- #
# Deterministic extractors
# --------------------------------------------------------------------------- #

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Swedish + international-ish: +46 8 123 45 67, 08-123 45 67, 0701234567
_PHONE_RE = re.compile(r"(?:\+\d{1,3}[ -]?)?(?:\(?0\d{1,3}\)?[ -]?)?\d{2,3}(?:[ -]?\d{2,3}){2,3}")
# Swedish organisationsnummer: 10 digits (or 16 + 10 digits), Luhn-valid.
_ORGNR_RE = re.compile(r"\b(?:16)?(\d{10})\b")
_POSTAL_RE = re.compile(r"\b(\d{3})[ ]?(\d{2})\b")
_SOCIAL_RE = re.compile(
    r"https?://(?:[a-z]{2,3}\.)?(linkedin|facebook|instagram)\.com/[A-Za-z0-9._\-/]+",
    re.IGNORECASE,
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == 0:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


class _FactParser(HTMLParser):
    """Collects the few signals level 1 can extract deterministically."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.site_name = ""
        self.meta_description = ""
        self.mailto: list[str] = []
        self.social: list[str] = []
        self.json_ld: list[str] = []
        self._capture: str | None = None

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key.lower(): (value or "") for key, value in attrs_list}
        tag = tag.lower()
        if tag == "title":
            self._capture = "title"
        elif tag == "meta":
            prop = attrs.get("property", "").lower()
            name = attrs.get("name", "").lower()
            if prop == "og:site_name" and not self.site_name:
                self.site_name = attrs.get("content", "").strip()
            if name == "description" and not self.meta_description:
                self.meta_description = attrs.get("content", "").strip()
        elif tag == "a":
            href = attrs.get("href", "")
            if href.lower().startswith("mailto:"):
                address = href.split(":", 1)[1].split("?")[0].strip()
                if address:
                    self.mailto.append(address)
            elif _SOCIAL_RE.search(href):
                self.social.append(href)
        elif tag == "script" and "ld+json" in attrs.get("type", "").lower():
            self._capture = "jsonld"

    def handle_data(self, data: str) -> None:
        if self._capture == "title" and not self.title:
            self.title = data.strip()
        elif self._capture == "jsonld":
            self.json_ld.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"title", "script"}:
            self._capture = None


def _json_ld_name(blocks: list[str]) -> str | None:
    for block in blocks:
        try:
            payload = json.loads(block.strip())
        except (TypeError, ValueError):
            # Malformed JSON-LD on a third-party page is expected, not an error:
            # skip this block and keep extracting from the rest of the page.
            continue
        candidates = payload if isinstance(payload, list) else [payload]
        for entry in candidates:
            if not isinstance(entry, dict):
                continue
            types = entry.get("@type")
            types = types if isinstance(types, list) else [types]
            if any(str(t).lower() in {"organization", "localbusiness", "corporation"} for t in types):
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
    return None


def _clean_title(title: str) -> str:
    """Strip the trailing ' - Tagline' / ' | Site' noise from <title>."""
    for separator in (" | ", " – ", " — ", " - ", " · "):
        if separator in title:
            return title.split(separator)[0].strip()
    return title.strip()


def extract_facts(html: str) -> list[ExtractedFact]:
    """Deterministic, LLM-free extraction. Every fact names its extractor."""
    parser = _FactParser()
    parser.feed(html or "")
    facts: list[ExtractedFact] = []
    seen: set[tuple[str, str]] = set()

    def add(field_name: str, value: str, extractor: str, evidence: str) -> None:
        key = (field_name, value)
        if not value or key in seen:
            return
        seen.add(key)
        facts.append(
            ExtractedFact(
                field=field_name,
                value=value,
                extractor=extractor,
                confidence=CONFIDENCE.get(extractor, 0.5),
                evidence=evidence,
            )
        )

    organisation = _json_ld_name(parser.json_ld)
    if organisation:
        add("company_name", organisation, "json_ld_organization", "JSON-LD @type Organization/LocalBusiness")
    elif parser.site_name:
        add("company_name", parser.site_name, "meta_site_name", '<meta property="og:site_name">')
    elif parser.title:
        add("company_name", _clean_title(parser.title), "title", "<title> with tagline stripped")

    for address in parser.mailto:
        add("email", address, "mailto_link", '<a href="mailto:…">')
    for address in _EMAIL_RE.findall(html or ""):
        add("email", address, "email_regex", "text pattern")
        if len([f for f in facts if f.field == "email"]) >= 5:
            break

    for match in _PHONE_RE.finditer(html or ""):
        digits = re.sub(r"\D", "", match.group(0))
        if 7 <= len(digits) <= 15:
            add("phone", match.group(0).strip(), "phone_regex", "text pattern")
        if len([f for f in facts if f.field == "phone"]) >= 5:
            break

    for match in _ORGNR_RE.finditer(html or ""):
        if _luhn_ok(match.group(1)):
            add("org_number", match.group(1), "org_number_luhn", "10-digit pattern passing Luhn")

    for match in _POSTAL_RE.finditer(html or ""):
        add("postal_code", f"{match.group(1)} {match.group(2)}", "postal_code_regex", "Swedish postnummer pattern")
        if len([f for f in facts if f.field == "postal_code"]) >= 3:
            break

    for link in parser.social:
        add("social_link", link, "social_link", "anchored href on a known network")

    return facts


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

LIMITATIONS: tuple[str, ...] = (
    "level 1: single operator-selected page only — no crawl, no sitemap walk",
    "no JavaScript execution: content rendered client-side is invisible here",
    "no authentication: login-walled or paywalled content is never accessed",
    "no LLM in the loop: extraction is deterministic and reproducible",
    "no score, price, max price, RAV or valuation is computed — facts only",
    "per-host throttle is in-process only, so it does not survive a restart",
)


def extract_public_page(
    url: str,
    *,
    policy: PolitenessPolicy | None = None,
    limiter: HostRateLimiter | None = None,
    clock=time.monotonic,
    sleep=time.sleep,
    fetch=None,
) -> ExtractionResult:
    """Fetch one public page politely and extract facts with provenance.

    Every collaborator is injectable so the whole path is testable without
    network access. ``fetch`` defaults to ``analyzer.fetch_public_html``.
    """
    policy = policy or PolitenessPolicy()
    limiter = limiter or HostRateLimiter(min_interval=policy.min_interval_seconds)

    safe_url = normalize_public_url(url)

    if is_tos_restricted(safe_url):
        raise WebsiteAuditError(
            "TOS_RESTRICTED_HOST",
            "This host is on the human-maintained terms-of-service denylist; not fetched",
            403,
        )

    verdict = robots_verdict(safe_url, user_agent=policy.user_agent)
    if not verdict.allowed:
        raise WebsiteAuditError(
            "ROBOTS_DISALLOWED",
            "robots.txt does not allow this user agent to fetch the page",
            403,
        )

    delay = limiter.seconds_to_wait(host_of(safe_url), clock())
    if verdict.crawl_delay_seconds is not None and policy.honour_crawl_delay:
        delay = max(delay, min(verdict.crawl_delay_seconds, policy.max_crawl_delay_seconds))
    if delay > 0:
        sleep(delay)

    if fetch is None:
        from app.prospecting.analyzer import fetch_public_html as fetch  # local import: cycle-safe

    html, final_url, duration_ms, content_sha = fetch(safe_url)
    limiter.mark(host_of(final_url), clock())

    facts = extract_facts(html)
    result = ExtractionResult(
        level=EXTRACTION_LEVEL,
        requested_url=safe_url,
        final_url=final_url,
        fetched_at=datetime.now(UTC).isoformat(),
        content_sha256=content_sha,
        facts=tuple(facts),
        politeness={
            "user_agent": policy.user_agent,
            "robots": verdict.source,
            "robots_crawl_delay_seconds": verdict.crawl_delay_seconds,
            "waited_seconds": round(delay, 3),
            "fetch_duration_ms": duration_ms,
            "min_interval_seconds": policy.min_interval_seconds,
        },
        limitations=LIMITATIONS,
    )
    # Fail closed before returning: a decisional field must never escape.
    assert_no_decisional_fields(result.as_dict())
    return result
