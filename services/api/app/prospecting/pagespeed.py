"""Optional Google PageSpeed Insights enrichment for browser-based metrics."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import settings
from app.prospecting.analyzer import normalize_public_url

PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedError(Exception):
    pass


def configured() -> bool:
    return bool(settings.PAGESPEED_API_KEY)


def run_pagespeed(url: str) -> dict | None:
    if not settings.PAGESPEED_API_KEY:
        return None
    safe_url = normalize_public_url(url)
    params = [
        ("url", safe_url),
        ("strategy", "mobile"),
        ("category", "PERFORMANCE"),
        ("category", "ACCESSIBILITY"),
        ("category", "SEO"),
        ("category", "BEST_PRACTICES"),
        ("key", settings.PAGESPEED_API_KEY),
    ]
    request = Request(f"{PAGESPEED_ENDPOINT}?{urlencode(params)}", headers={"Accept": "application/json", "User-Agent": "SalesOS-WebAudit/1.0"})
    try:
        with urlopen(request, timeout=25) as response:
            raw = response.read(6_000_001)
    except HTTPError as exc:
        raise PageSpeedError(f"PageSpeed returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise PageSpeedError("PageSpeed provider could not be reached") from exc
    if len(raw) > 6_000_000:
        raise PageSpeedError("PageSpeed response exceeded the size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PageSpeedError("PageSpeed returned an invalid response") from exc
    lighthouse = payload.get("lighthouseResult") or {}
    categories = lighthouse.get("categories") or {}
    audits = lighthouse.get("audits") or {}

    def score(category: str) -> int | None:
        value = (categories.get(category) or {}).get("score")
        return round(float(value) * 100) if isinstance(value, (int, float)) else None

    def display(audit: str) -> str | None:
        value = (audits.get(audit) or {}).get("displayValue")
        return str(value) if value is not None else None

    screenshot = ((audits.get("final-screenshot") or {}).get("details") or {}).get("data")
    if not isinstance(screenshot, str) or not screenshot.startswith("data:image/") or len(screenshot) > 750_000:
        screenshot = None
    return {
        "provider": "google_pagespeed_insights",
        "strategy": "mobile",
        "scores": {
            "performance": score("performance"),
            "accessibility": score("accessibility"),
            "seo": score("seo"),
            "best_practices": score("best-practices"),
        },
        "web_vitals": {
            "first_contentful_paint": display("first-contentful-paint"),
            "largest_contentful_paint": display("largest-contentful-paint"),
            "total_blocking_time": display("total-blocking-time"),
            "cumulative_layout_shift": display("cumulative-layout-shift"),
            "speed_index": display("speed-index"),
        },
        "final_screenshot": screenshot,
        "fetch_time": lighthouse.get("fetchTime"),
        "requested_url": safe_url,
        "final_url": lighthouse.get("finalUrl"),
    }
