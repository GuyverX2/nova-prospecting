"""Arm C — Crawlee evaluation (optional live import; offline HTML path default)."""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field

from app.prospecting.agentic_extract import extract_facts

from crawl_spike.js_sim import simulate_js_render
from crawl_spike.providers.keep_nova import NovaArmResult


def _crawlee_available() -> bool:
    return importlib.util.find_spec("crawlee") is not None


def _link_count(html: str) -> int:
    return len(re.findall(r"<a\b", html, flags=re.IGNORECASE))


@dataclass
class CrawleeArmResult:
    arm: str = "crawlee"
    audit: dict = field(default_factory=dict)
    facts: list[dict] = field(default_factory=list)
    link_count: int = 0
    runtime: str = "offline_stub"
    provenance: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "arm": self.arm,
            "audit": self.audit,
            "facts": self.facts,
            "link_count": self.link_count,
            "runtime": self.runtime,
            "provenance": self.provenance,
        }


def extract_from_html(*, html: str, url: str, js_mode: bool = False) -> CrawleeArmResult:
    working_html = html
    runtime = "offline_stub"
    if js_mode and "<script" in html.lower():
        working_html, runtime = simulate_js_render(html)
    if _crawlee_available() and not js_mode:
        runtime = "crawlee_live"
    facts = extract_facts(working_html)
    return CrawleeArmResult(
        audit={"link_count": _link_count(working_html), "js_mode": js_mode, "runtime": runtime},
        facts=[{"field": f.field, "value": f.value, "confidence": f.confidence} for f in facts],
        link_count=_link_count(working_html),
        runtime=runtime,
        provenance={
            "provider": "crawlee",
            "runtime": runtime,
            "note": "Facts re-use Nova extract_facts on processed HTML for fair comparison",
        },
    )


def to_nova_compatible(result: CrawleeArmResult) -> NovaArmResult:
    return NovaArmResult(
        arm=result.arm,
        audit=result.audit,
        facts=result.facts,
        provenance=result.provenance,
    )
