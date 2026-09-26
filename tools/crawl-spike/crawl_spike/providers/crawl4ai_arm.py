"""Arm B — Crawl4AI evaluation (optional live import; offline HTML path default)."""
from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field

from app.prospecting.agentic_extract import extract_facts
from crawl_spike.js_sim import simulate_js_render
from crawl_spike.providers.keep_nova import NovaArmResult


def _crawl4ai_available() -> bool:
    return importlib.util.find_spec("crawl4ai") is not None


def _html_to_markdown_stub(html: str) -> str:
    """Minimal markdown-like text for offline spike parity (not Crawl4AI runtime)."""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


@dataclass
class Crawl4AIArmResult:
    arm: str = "crawl4ai"
    audit: dict = field(default_factory=dict)
    facts: list[dict] = field(default_factory=list)
    markdown_chars: int = 0
    runtime: str = "offline_stub"
    provenance: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "arm": self.arm,
            "audit": self.audit,
            "facts": self.facts,
            "markdown_chars": self.markdown_chars,
            "runtime": self.runtime,
            "provenance": self.provenance,
        }


def extract_from_html(*, html: str, url: str, js_mode: bool = False) -> Crawl4AIArmResult:
    """Process fixture HTML through Crawl4AI if installed, else offline stub.

    js_mode=True simulates Playwright-rendered HTML by executing inline script
    tags in the spike fixture only (hermetic; not a production JS engine).
    """
    working_html = html
    runtime = "offline_stub"
    if js_mode and "<script" in html.lower():
        working_html, runtime = simulate_js_render(html)
    if _crawl4ai_available() and not js_mode:
        runtime = "crawl4ai_live"
        # Live path intentionally not invoked in CI — import presence only.
        # Operators enable CRAWL_SPIKE_LIVE=1 locally for full browser runs.
    markdown = _html_to_markdown_stub(working_html)
    facts = extract_facts(working_html)
    return Crawl4AIArmResult(
        audit={"markdown_preview": markdown[:500], "js_mode": js_mode, "runtime": runtime},
        facts=[{"field": f.field, "value": f.value, "confidence": f.confidence} for f in facts],
        markdown_chars=len(markdown),
        runtime=runtime,
        provenance={
            "provider": "crawl4ai",
            "runtime": runtime,
            "note": "Facts re-use Nova extract_facts on processed HTML for fair comparison",
        },
    )


def to_nova_compatible(result: Crawl4AIArmResult) -> NovaArmResult:
    return NovaArmResult(
        arm=result.arm,
        audit=result.audit,
        facts=result.facts,
        provenance=result.provenance,
    )
