"""Capability scoring rubric for crawl library comparison."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DimensionScore:
    dimension: str
    score: int  # 0–3
    evidence: str


@dataclass(frozen=True)
class ArmCapabilities:
    arm: str
    scores: tuple[DimensionScore, ...]

    def total(self) -> int:
        return sum(item.score for item in self.scores)

    def as_dict(self) -> dict:
        return {
            "arm": self.arm,
            "total": self.total(),
            "dimensions": {
                item.dimension: {"score": item.score, "evidence": item.evidence}
                for item in self.scores
            },
        }


# Hand-scored from reading Nova analyzer/agentic_extract + library docs (2026-09).
# Re-score after optional live runs with CRAWL_SPIKE_LIVE=1.
CAPABILITY_MATRIX: dict[str, ArmCapabilities] = {
    "keep_nova": ArmCapabilities(
        arm="keep_nova",
        scores=(
            DimensionScore("ssrf_safety", 3, "DNS + literal IP guards, redirect re-validation, port 80/443 only"),
            DimensionScore("robots_compliance", 3, "RobotFileParser + Crawl-delay in agentic_extract PoC"),
            DimensionScore("provenance", 3, "evidence[] + facts[].evidence + snapshot_sha256 in analyzer"),
            DimensionScore("retries", 1, "Single attempt by design; operator re-run"),
            DimensionScore("timeout", 3, "10s bounded fetch; 1.5MB cap documented"),
            DimensionScore("structured_output", 3, "findings/evidence/technical JSON + level-1 facts"),
            DimensionScore("js_rendering", 0, "Explicit limitation: JavaScript not executed"),
            DimensionScore("anti_bot_ops_cost", 3, "Low footprint stdlib fetch; no browser farm"),
            DimensionScore("tenant_isolation", 3, "No shared URL cache; tenant_id on prospect rows"),
            DimensionScore("license", 3, "Internal code; no third-party crawl runtime"),
            DimensionScore("integration_effort", 3, "Already integrated behind PROSPECTING_FETCH_ENABLED"),
        ),
    ),
    "crawl4ai": ArmCapabilities(
        arm="crawl4ai",
        scores=(
            DimensionScore("ssrf_safety", 1, "Generic crawler; SalesOS guards must be re-wrapped"),
            DimensionScore("robots_compliance", 2, "Configurable; not SalesOS operator defaults"),
            DimensionScore("provenance", 2, "Markdown + metadata; needs mapping to Evidence Ledger"),
            DimensionScore("retries", 2, "Built-in retry hooks; policy must be capped"),
            DimensionScore("timeout", 2, "Configurable; Playwright path slower/heavier"),
            DimensionScore("structured_output", 2, "Markdown/JSON extraction; differs from Nova audit schema"),
            DimensionScore("js_rendering", 3, "Playwright-backed rendering available"),
            DimensionScore("anti_bot_ops_cost", 1, "Browser pool, stealth/proxy ops; memory on worker"),
            DimensionScore("tenant_isolation", 1, "No tenant concept; cache must be designed"),
            DimensionScore("license", 2, "Apache-2.0 + mandatory attribution notice in distributions"),
            DimensionScore("integration_effort", 1, "New provider + feature flag + SSRF adapter ~400+ LOC"),
        ),
    ),
    "crawlee": ArmCapabilities(
        arm="crawlee",
        scores=(
            DimensionScore("ssrf_safety", 1, "Generic crawler; SalesOS guards must be re-wrapped"),
            DimensionScore("robots_compliance", 2, "Protego robots parser; policy wiring required"),
            DimensionScore("provenance", 2, "Request queue metadata; map to SalesOS evidence model"),
            DimensionScore("retries", 3, "Mature retry/backoff in Crawlee request queue"),
            DimensionScore("timeout", 2, "Configurable per handler; browser arm heavier"),
            DimensionScore("structured_output", 2, "Handler-defined; not Nova audit/facts schema"),
            DimensionScore("js_rendering", 3, "Playwright/Puppeteer integration path"),
            DimensionScore("anti_bot_ops_cost", 1, "Browser workers + Apify-style ops if scaled out"),
            DimensionScore("tenant_isolation", 1, "No tenant concept; queue names must be scoped"),
            DimensionScore("license", 2, "Apache-2.0; standard NOTICE requirements"),
            DimensionScore("integration_effort", 1, "New provider + queue lifecycle ~450+ LOC"),
        ),
    ),
}


def recommend_decision(
    *,
    extraction_recall: dict[str, float],
    capability_totals: dict[str, int],
) -> dict[str, str]:
    """Return per-competitor decision with rationale (spike-only heuristic)."""
    baseline_recall = extraction_recall.get("keep_nova", 0.0)
    decisions: dict[str, str] = {"keep_nova": "KEEP"}

    for arm in ("crawl4ai", "crawlee"):
        recall_delta = extraction_recall.get(arm, 0.0) - baseline_recall
        cap_delta = capability_totals.get(arm, 0) - capability_totals.get("keep_nova", 0)
        if recall_delta >= 0.15 and cap_delta >= -5:
            decisions[arm] = "INTEGRATE"
        elif recall_delta >= 0.05 or cap_delta >= -3:
            decisions[arm] = "HARVEST"
        else:
            decisions[arm] = "REJECT"
    return decisions
