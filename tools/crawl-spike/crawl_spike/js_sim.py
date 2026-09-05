"""Shared helpers for crawl spike arms."""
from __future__ import annotations

import re


def simulate_js_render(html: str) -> tuple[str, str]:
    """Hermetic JS render simulation for spike fixtures only."""
    match = re.search(r"innerHTML\s*=\s*'([^']+)'", html, flags=re.DOTALL)
    if not match:
        return html, "offline_stub"
    fragment = match.group(1).replace("\\\"", '"')
    title = "Rendered page"
    h1 = re.search(r"<h1[^>]*>([^<]+)</h1>", fragment, flags=re.IGNORECASE)
    if h1:
        title = h1.group(1).strip()
    working_html = (
        f"<!doctype html><html><head><title>{title}</title></head><body>{fragment}</body></html>"
    )
    return working_html, "js_simulated"
