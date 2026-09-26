"""Evidence-first website audit with SSRF-safe, bounded fetching.

The analyzer intentionally audits one operator-selected public page. It does not
crawl a whole site, execute JavaScript, bypass robots.txt, or access private
network ranges. Findings are deterministic and always include evidence.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

MAX_HTML_BYTES = 1_500_000
MAX_REDIRECTS = 4
FETCH_TIMEOUT_SECONDS = 10
USER_AGENT = "SalesOS-WebAudit/1.0 (+operator-assisted; respects robots.txt)"
BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata", "instance-data"}


class WebsiteAuditError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 422):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass
class ParsedPage:
    title: str = ""
    description: str = ""
    lang: str = ""
    canonical: str = ""
    viewport: bool = False
    headings: list[tuple[str, str]] = field(default_factory=list)
    links: list[tuple[str, str]] = field(default_factory=list)
    images: list[tuple[str, str | None]] = field(default_factory=list)
    forms: list[dict] = field(default_factory=list)
    scripts: int = 0
    stylesheets: int = 0
    json_ld: int = 0
    inputs_without_label_hint: int = 0
    body_text: str = ""


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.page = ParsedPage()
        self._capture: str | None = None
        self._buffer: list[str] = []
        self._form: dict | None = None
        self._body_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs_list: list[tuple[str, str | None]]) -> None:
        attrs = {key.lower(): value for key, value in attrs_list}
        tag = tag.lower()
        if tag == "html":
            self.page.lang = (attrs.get("lang") or "").strip()
        elif tag == "title":
            self._capture = "title"
            self._buffer = []
        elif tag in {"h1", "h2", "h3"}:
            self._capture = tag
            self._buffer = []
        elif tag == "meta":
            name = (attrs.get("name") or "").lower()
            prop = (attrs.get("property") or "").lower()
            if (name == "description" or prop == "og:description") and not self.page.description:
                self.page.description = (attrs.get("content") or "").strip()
            if name == "viewport":
                self.page.viewport = True
        elif tag == "link":
            rel = (attrs.get("rel") or "").lower()
            if "canonical" in rel:
                self.page.canonical = (attrs.get("href") or "").strip()
            if "stylesheet" in rel:
                self.page.stylesheets += 1
        elif tag == "a":
            self.page.links.append(((attrs.get("href") or "").strip(), (attrs.get("aria-label") or "").strip()))
        elif tag == "img":
            self.page.images.append(((attrs.get("src") or "").strip(), attrs.get("alt")))
        elif tag == "script":
            self.page.scripts += 1
            if (attrs.get("type") or "").lower() == "application/ld+json":
                self.page.json_ld += 1
        elif tag == "form":
            self._form = {
                "action": (attrs.get("action") or "").strip(),
                "method": (attrs.get("method") or "get").lower(),
                "input_count": 0,
            }
        elif tag in {"input", "textarea", "select"} and self._form is not None:
            input_type = (attrs.get("type") or "text").lower()
            if input_type not in {"hidden", "submit", "button"}:
                self._form["input_count"] += 1
                if not attrs.get("aria-label") and not attrs.get("id") and not attrs.get("placeholder"):
                    self.page.inputs_without_label_hint += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._capture == tag:
            text = " ".join("".join(self._buffer).split())
            if tag == "title":
                self.page.title = text
            elif text:
                self.page.headings.append((tag, text[:300]))
            self._capture = None
            self._buffer = []
        if tag == "form" and self._form is not None:
            self.page.forms.append(self._form)
            self._form = None

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)
        cleaned = " ".join(data.split())
        if cleaned:
            self._body_parts.append(cleaned)

    def close(self) -> None:
        super().close()
        self.page.body_text = " ".join(self._body_parts)[:200_000]


def normalize_public_url(url: str) -> str:
    value = (url or "").strip()
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise WebsiteAuditError("URL_SCHEME_BLOCKED", "Only http and https URLs are allowed")
    if parsed.username or parsed.password:
        raise WebsiteAuditError("URL_CREDENTIALS_BLOCKED", "URLs containing credentials are not allowed")
    hostname = (parsed.hostname or "").strip(".").lower()
    if not hostname or hostname in BLOCKED_HOSTS or hostname.endswith(".local") or hostname.endswith(".internal"):
        raise WebsiteAuditError("URL_HOST_BLOCKED", "The URL host is not a public website host")
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        raise WebsiteAuditError("URL_HOST_BLOCKED", "Private, local, reserved, or metadata addresses are blocked", 403)
    if parsed.port is not None and parsed.port not in {80, 443}:
        raise WebsiteAuditError("URL_PORT_BLOCKED", "Only standard web ports 80 and 443 are allowed")
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, path, parsed.query, ""))


def _assert_public_host(url: str) -> None:
    parsed = urlsplit(normalize_public_url(url))
    hostname = parsed.hostname or ""
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise WebsiteAuditError("DNS_LOOKUP_FAILED", "The website hostname could not be resolved", 400) from exc
    if not addresses:
        raise WebsiteAuditError("DNS_LOOKUP_FAILED", "The website hostname returned no addresses", 400)
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise WebsiteAuditError("PRIVATE_NETWORK_BLOCKED", "Private, local, reserved, or metadata addresses are blocked", 403)


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self) -> None:
        super().__init__()
        self.redirect_count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirect_count += 1
        if self.redirect_count > MAX_REDIRECTS:
            raise WebsiteAuditError("TOO_MANY_REDIRECTS", "The website exceeded the redirect limit", 400)
        target = urljoin(req.full_url, newurl)
        _assert_public_host(target)
        return super().redirect_request(req, fp, code, msg, headers, target)


def _bounded_fetch(url: str, *, accept: str, max_bytes: int) -> tuple[bytes, str, str, int]:
    safe_url = normalize_public_url(url)
    _assert_public_host(safe_url)
    opener = build_opener(_SafeRedirectHandler())
    # S310 on the next two lines: normalize_public_url and _assert_public_host
    # have already proven this URL is a public http(s) endpoint.
    request = Request(safe_url, headers={"User-Agent": USER_AGENT, "Accept": accept})  # noqa: S310
    started = time.monotonic()
    try:
        with opener.open(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            content_type = (response.headers.get("Content-Type") or "").lower()
            data = response.read(max_bytes + 1)
            final_url = normalize_public_url(response.geturl())
            _assert_public_host(final_url)
    except WebsiteAuditError:
        raise
    except HTTPError as exc:
        raise WebsiteAuditError("UPSTREAM_HTTP_ERROR", f"Website returned HTTP {exc.code}", 400) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WebsiteAuditError("WEBSITE_FETCH_FAILED", "The public website could not be fetched safely", 400) from exc
    duration_ms = round((time.monotonic() - started) * 1000)
    if len(data) > max_bytes:
        raise WebsiteAuditError("WEBSITE_TOO_LARGE", f"Website response exceeded {max_bytes} bytes", 413)
    return data, final_url, content_type, duration_ms


def _robots_allowed(url: str) -> bool:
    parsed = urlsplit(url)
    robots_url = urlunsplit((parsed.scheme, parsed.netloc, "/robots.txt", "", ""))
    try:
        body, _, _, _ = _bounded_fetch(robots_url, accept="text/plain,*/*;q=0.2", max_bytes=256_000)
    except WebsiteAuditError as exc:
        # A missing robots file (HTTP error) is treated as no declared restriction;
        # security/network failures still block the audit rather than being bypassed.
        if exc.code == "UPSTREAM_HTTP_ERROR":
            return True
        raise
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(body.decode("utf-8", errors="replace").splitlines())
    return parser.can_fetch(USER_AGENT, url)


def fetch_public_html(url: str) -> tuple[str, str, int, str]:
    safe_url = normalize_public_url(url)
    if not _robots_allowed(safe_url):
        raise WebsiteAuditError("ROBOTS_DISALLOWED", "The website robots.txt does not allow this audit user agent", 403)
    data, final_url, content_type, duration_ms = _bounded_fetch(
        safe_url,
        accept="text/html,application/xhtml+xml;q=0.9",
        max_bytes=MAX_HTML_BYTES,
    )
    if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
        raise WebsiteAuditError("CONTENT_TYPE_BLOCKED", "The URL did not return an HTML document", 415)
    charset_match = re.search(r"charset=([\w.-]+)", content_type)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        html = data.decode(charset, errors="replace")
    except LookupError:
        html = data.decode("utf-8", errors="replace")
    return html, final_url, duration_ms, hashlib.sha256(data).hexdigest()


def _finding(key: str, title: str, detail: str, severity: str, evidence_ids: list[str], confidence: float) -> dict:
    return {
        "key": key,
        "title": title,
        "detail": detail,
        "severity": severity,
        "evidence_ids": evidence_ids,
        "confidence": confidence,
    }


def analyze_html(html: str, url: str, *, final_url: str | None = None, fetch_duration_ms: int | None = None) -> dict:
    if not html or not html.strip():
        raise WebsiteAuditError("EMPTY_HTML", "No HTML content was available for analysis")
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise WebsiteAuditError("WEBSITE_TOO_LARGE", "HTML snapshot exceeded the analysis size limit", 413)
    analyzed_url = normalize_public_url(url)
    parser = _PageParser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # HTMLParser is tolerant; unexpected failures are made explicit.
        raise WebsiteAuditError("HTML_PARSE_FAILED", "The HTML snapshot could not be parsed") from exc
    page = parser.page
    evidence: list[dict] = []
    findings: list[dict] = []

    def add_evidence(evidence_id: str, label: str, value, source: str = "html") -> str:
        evidence.append({
            "id": evidence_id,
            "label": label,
            "value": value,
            "source": source,
            "url": final_url or analyzed_url,
        })
        return evidence_id

    title_id = add_evidence("ev_title", "Document title", page.title or None)
    description_id = add_evidence("ev_description", "Meta description", page.description or None)
    viewport_id = add_evidence("ev_viewport", "Responsive viewport", page.viewport)
    lang_id = add_evidence("ev_lang", "Document language", page.lang or None)
    h1s = [text for level, text in page.headings if level == "h1"]
    heading_id = add_evidence("ev_h1", "H1 headings", h1s)
    images_without_alt = sum(1 for _, alt in page.images if alt is None or not alt.strip())
    images_id = add_evidence("ev_images", "Images / missing alt text", {"total": len(page.images), "missing_alt": images_without_alt})
    forms_id = add_evidence("ev_forms", "Forms", page.forms)
    structured_id = add_evidence("ev_jsonld", "JSON-LD blocks", page.json_ld)
    secure_id = add_evidence("ev_https", "HTTPS", urlsplit(final_url or analyzed_url).scheme == "https")
    timing_id = add_evidence("ev_fetch", "Server fetch duration (not Core Web Vitals)", fetch_duration_ms, "network")

    text_lower = page.body_text.lower()
    cta_terms = ("offert", "boka", "kontakta", "ring oss", "begär", "kostnadsfri", "get a quote", "contact")
    cta_hits = sorted({term for term in cta_terms if term in text_lower})
    cta_id = add_evidence("ev_cta", "Detected conversion terms", cta_hits)
    local_terms = bool(re.search(r"\b(i|nära|lokal|område|kommun|region)\b", text_lower))
    local_id = add_evidence("ev_local", "Local intent language detected", local_terms)

    seo = 100
    accessibility = 100
    mobile = 100
    performance = 100

    if not page.title:
        seo -= 24
        findings.append(_finding("missing_title", "Sidtitel saknas", "Sidan saknar en dokumenttitel som beskriver erbjudandet i sökresultat.", "high", [title_id], 1.0))
    elif len(page.title) < 20 or len(page.title) > 65:
        seo -= 10
        findings.append(_finding("title_length", "Sidtiteln kan skärpas", f"Titeln är {len(page.title)} tecken; ett tydligare, fokuserat spann är ofta 20–65.", "medium", [title_id], 0.95))
    if not page.description:
        seo -= 18
        findings.append(_finding("missing_description", "Metabeskrivning saknas", "Sökmotorer får inget kuraterat budskap för sidan.", "medium", [description_id], 1.0))
    if len(h1s) != 1:
        seo -= 14
        findings.append(_finding("h1_structure", "Rubrikhierarkin behöver ses över", f"Analysen hittade {len(h1s)} H1-rubriker; startsidan bör normalt ha en tydlig huvudrubrik.", "medium", [heading_id], 0.95))
    if page.json_ld == 0:
        seo -= 10
        findings.append(_finding("structured_data", "Strukturerad data saknas", "Ingen JSON-LD hittades på sidan. LocalBusiness- och tjänstedata kan förbättra sökmotorernas förståelse.", "medium", [structured_id], 0.98))
    if not page.lang:
        accessibility -= 12
        seo -= 4
        findings.append(_finding("missing_lang", "Sidspråk saknas", "HTML-dokumentet anger inte språk, vilket påverkar hjälpmedel och söktolkning.", "medium", [lang_id], 1.0))
    if images_without_alt:
        ratio = images_without_alt / max(len(page.images), 1)
        accessibility -= min(35, round(10 + ratio * 25))
        findings.append(_finding("image_alt", "Bildbeskrivningar saknas", f"{images_without_alt} av {len(page.images)} bilder saknar alternativtext.", "high" if ratio > 0.5 else "medium", [images_id], 1.0))
    if page.inputs_without_label_hint:
        accessibility -= min(25, page.inputs_without_label_hint * 6)
        findings.append(_finding("form_labels", "Formulärfält behöver tydligare etiketter", f"{page.inputs_without_label_hint} fält saknar identifierbar etikettindikator i HTML.", "high", [forms_id], 0.85))
    if not page.viewport:
        mobile -= 42
        findings.append(_finding("missing_viewport", "Mobilanpassning kan vara bristfällig", "Sidan saknar en responsiv viewport-deklaration.", "high", [viewport_id], 1.0))
    if not cta_hits:
        findings.append(_finding("weak_cta", "Tydlig nästa handling saknas", "Ingen vanlig offert-, boknings- eller kontaktuppmaning kunde verifieras i sidtexten.", "high", [cta_id], 0.82))
    if page.forms and max((form["input_count"] for form in page.forms), default=0) > 7:
        findings.append(_finding("long_form", "Kontaktflödet kan förenklas", "Minst ett formulär har fler än sju synliga fält och kan skapa onödig friktion.", "medium", [forms_id], 0.9))
    if not local_terms:
        findings.append(_finding("local_visibility", "Lokal relevans är otydlig", "Analysen hittade få tydliga lokala signaler i sidans text. Detta bör verifieras mot verksamhetsområdet.", "medium", [local_id], 0.65))
    if urlsplit(final_url or analyzed_url).scheme != "https":
        performance -= 8
        seo -= 10
        findings.append(_finding("no_https", "HTTPS saknas", "Sidan levereras utan verifierad HTTPS på den analyserade URL:en.", "high", [secure_id], 1.0))
    if fetch_duration_ms is not None:
        if fetch_duration_ms > 2500:
            performance -= 34
            findings.append(_finding("slow_server", "Långsam serverrespons", f"Den avgränsade HTML-hämtningen tog {fetch_duration_ms} ms. Detta är inte ett Core Web Vitals-resultat men bör undersökas.", "high", [timing_id], 0.9))
        elif fetch_duration_ms > 1200:
            performance -= 18
            findings.append(_finding("server_latency", "Serverresponsen kan förbättras", f"HTML-hämtningen tog {fetch_duration_ms} ms. Komplettera med Lighthouse för användarmätning.", "medium", [timing_id], 0.85))
    html_bytes = len(html.encode("utf-8"))
    if html_bytes > 800_000:
        performance -= 18
    elif html_bytes > 350_000:
        performance -= 8
    if page.scripts > 30:
        performance -= 16
    elif page.scripts > 15:
        performance -= 8
    if len(page.images) > 40:
        performance -= 8

    metrics = {
        "performance": max(0, min(100, performance)),
        "seo": max(0, min(100, seo)),
        "accessibility": max(0, min(100, accessibility)),
        "mobile": max(0, min(100, mobile)),
    }
    improvement_score = round(100 - sum(metrics.values()) / len(metrics))
    # Commercial opportunity scoring also considers verified UX/content gaps.
    improvement_score = min(100, max(improvement_score, min(95, 45 + len(findings) * 6)))
    if not findings:
        findings.append(_finding("healthy_baseline", "Stabil teknisk grund", "Den avgränsade HTML-analysen hittade inga kritiska grundfel. En Lighthouse- och innehållsgranskning rekommenderas ändå.", "positive", list(metrics.keys()), 0.7))

    return {
        "analyzed_url": analyzed_url,
        "final_url": final_url or analyzed_url,
        "improvement_score": improvement_score,
        "metrics": metrics,
        "findings": findings,
        "evidence": evidence,
        "technical": {
            "title": page.title,
            "meta_description": page.description,
            "lang": page.lang,
            "canonical": page.canonical,
            "heading_count": len(page.headings),
            "h1_count": len(h1s),
            "link_count": len(page.links),
            "image_count": len(page.images),
            "form_count": len(page.forms),
            "script_count": page.scripts,
            "stylesheet_count": page.stylesheets,
            "html_bytes": html_bytes,
            "scope": "single_page_static_html",
            "limitations": [
                "JavaScript was not executed",
                "Core Web Vitals require a browser/Lighthouse provider",
                "Findings describe the analyzed page, not the entire domain",
            ],
        },
        "snapshot_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
        "fetch_duration_ms": fetch_duration_ms,
    }
