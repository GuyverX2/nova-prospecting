"""Optional Google PageSpeed Insights enrichment for browser-based metrics."""
from __future__ import annotations

from urllib.parse import urlencode

from app.core.config import settings
from app.integrations.http import (
    IntegrationRejected,
    IntegrationUnavailable,
    RetryPolicy,
    request_json,
)
from app.prospecting.analyzer import normalize_public_url

PAGESPEED_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
MAX_PAGESPEED_BYTES = 6_000_000
USER_AGENT = "Nova-WebAudit/1.0"


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
    try:
        payload = request_json(
            f"{PAGESPEED_ENDPOINT}?{urlencode(params)}",
            headers={"User-Agent": USER_AGENT},
            timeout=settings.PAGESPEED_TIMEOUT_SECONDS,
            max_bytes=MAX_PAGESPEED_BYTES,
            retry=RetryPolicy(attempts=2),
            provider="PageSpeed",
        )
    except (IntegrationRejected, IntegrationUnavailable) as exc:
        # Enrichment is optional: the caller records the warning and keeps the
        # evidence-backed HTML analysis it already has.
        raise PageSpeedError(str(exc)) from exc
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
