"""Three-way crawl spike runner — synthetic fixtures only by default."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from crawl_spike.capabilities import CAPABILITY_MATRIX, recommend_decision
from crawl_spike.providers import crawl4ai_arm, crawlee_arm, keep_nova

REPO_ROOT = Path(__file__).resolve().parents[3]
# Single source of truth: the fixture lives with the decision record it supports
# (it used to be duplicated here, and the two copies drifted apart in comments).
DEFAULT_FIXTURE = REPO_ROOT / "docs/architecture-program/wave-0-3/fixtures/crawl-cases.yaml"
PAGES_DIR = REPO_ROOT / "tools/crawl-spike/fixtures/pages"


def load_fixture_doc(path: Path | None = None) -> dict[str, Any]:
    fixture_path = path or DEFAULT_FIXTURE
    with fixture_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _load_page(name: str) -> str:
    page_path = PAGES_DIR / name
    return page_path.read_text(encoding="utf-8")


def _fact_map(facts: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for fact in facts:
        out.setdefault(fact["field"], []).append(str(fact["value"]))
    return out


def _check_absent_facts(facts: list[dict], absent_fields: list[str]) -> bool:
    present = set(_fact_map(facts))
    return not any(field in present for field in absent_fields)


def _check_expected_facts(facts: list[dict], expected: list[dict]) -> tuple[int, int]:
    if not expected:
        return (1, 1) if not facts else (0, 1)
    hits = 0
    for item in expected:
        field_name = item["field"]
        values = _fact_map(facts).get(field_name, [])
        if "value" in item:
            if any(v == item["value"] for v in values):
                hits += 1
        elif "value_contains" in item:
            needle = item["value_contains"]
            if any(needle in v for v in values):
                hits += 1
    return hits, len(expected)


@dataclass
class CaseResult:
    case_id: str
    arm: str
    passed: bool
    fact_hits: int
    fact_total: int
    details: dict = field(default_factory=dict)

    def recall(self) -> float:
        if self.fact_total == 0:
            return 1.0
        return self.fact_hits / self.fact_total


@dataclass
class SpikeReport:
    case_results: list[CaseResult] = field(default_factory=list)
    capability_totals: dict[str, int] = field(default_factory=dict)
    extraction_recall: dict[str, float] = field(default_factory=dict)
    static_recall: dict[str, float] = field(default_factory=dict)
    decisions: dict[str, str] = field(default_factory=dict)
    summary: str = ""

    def as_dict(self) -> dict:
        return {
            "case_results": [item.__dict__ for item in self.case_results],
            "capability_totals": self.capability_totals,
            "extraction_recall": self.extraction_recall,
            "static_recall": self.static_recall,
            "decisions": self.decisions,
            "summary": self.summary,
        }


def run_spike(*, fixture_path: Path | None = None) -> SpikeReport:
    doc = load_fixture_doc(fixture_path)
    report = SpikeReport()
    recall_accum: dict[str, list[float]] = {arm: [] for arm in ("keep_nova", "crawl4ai", "crawlee")}
    static_accum: dict[str, list[float]] = {arm: [] for arm in ("keep_nova", "crawl4ai", "crawlee")}

    for case in doc["cases"]:
        case_id = case["id"]
        if case.get("ssrf_probe"):
            result = keep_nova.probe_ssrf(case["url"])
            blocked_codes = set(case.get("blocked_codes") or [])
            passed = result.blocked and (not blocked_codes or result.block_code in blocked_codes)
            for arm in recall_accum:
                report.case_results.append(
                    CaseResult(
                        case_id=case_id,
                        arm=arm,
                        passed=passed if arm == "keep_nova" else False,
                        fact_hits=int(passed),
                        fact_total=1,
                        details={"block_code": result.block_code, "ssrf_probe": True},
                    )
                )
            continue

        if case.get("capability_only"):
            continue

        html = _load_page(case["fixture"])
        url = case["url"]
        js_mode = bool(case.get("static_fetch_limitation"))
        expected = case.get("expected_facts") or case.get("expected_facts_when_js") or []

        arms = [
            ("keep_nova", keep_nova.extract_from_html(html=html, url=url)),
            ("crawl4ai", crawl4ai_arm.extract_from_html(html=html, url=url, js_mode=js_mode)),
            ("crawlee", crawlee_arm.extract_from_html(html=html, url=url, js_mode=js_mode)),
        ]

        for arm_name, arm_result in arms:
            effective_expected = expected
            if arm_name == "keep_nova" and case.get("static_fetch_limitation"):
                js_expected = case.get("expected_facts_when_js") or []
                hits, total = _check_expected_facts(arm_result.facts, js_expected)
                passed = hits == 0 and total > 0
                recall_accum[arm_name].append(0.0 if total else 1.0)
            else:
                if case.get("static_fetch_limitation"):
                    effective_expected = case.get("expected_facts_when_js") or expected
                hits, total = _check_expected_facts(arm_result.facts, effective_expected)
                passed = hits == total
                absent = case.get("expected_facts_absent") or []
                if absent and not _check_absent_facts(arm_result.facts, absent):
                    passed = False
                recall_accum[arm_name].append(hits / total if total else 1.0)
                if not case.get("static_fetch_limitation"):
                    static_accum[arm_name].append(hits / total if total else 1.0)

            audit_checks = case.get("expected_audit") or {}
            audit = arm_result.audit
            if audit_checks and arm_name == "keep_nova":
                technical = audit.get("technical") or {}
                if "h1_count" in audit_checks and technical.get("h1_count") != audit_checks["h1_count"]:
                    passed = False
                if audit_checks.get("has_viewport"):
                    viewport_ok = any(
                        ev.get("label") == "Responsive viewport" and ev.get("value")
                        for ev in audit.get("evidence", [])
                    )
                    if not viewport_ok:
                        passed = False
                if "json_ld_blocks_min" in audit_checks:
                    # analyze_html stores the JSON-LD count as the ev_jsonld evidence value.
                    json_ld_blocks = next(
                        (ev.get("value") for ev in audit.get("evidence", []) if ev.get("id") == "ev_jsonld"),
                        0,
                    )
                    if json_ld_blocks < audit_checks["json_ld_blocks_min"]:
                        passed = False

            report.case_results.append(
                CaseResult(
                    case_id=case_id,
                    arm=arm_name,
                    passed=passed,
                    fact_hits=hits,
                    fact_total=total,
                    details={"facts": arm_result.facts[:5]},
                )
            )

    for arm, values in recall_accum.items():
        report.extraction_recall[arm] = round(sum(values) / max(len(values), 1), 3)
    for arm, values in static_accum.items():
        report.static_recall[arm] = round(sum(values) / max(len(values), 1), 3)

    report.capability_totals = {arm: cap.total() for arm, cap in CAPABILITY_MATRIX.items()}
    report.decisions = recommend_decision(
        extraction_recall=report.static_recall,
        capability_totals=report.capability_totals,
    )
    winner = max(report.static_recall, key=report.static_recall.get)
    if winner == "keep_nova" and report.decisions.get("crawl4ai") in {"REJECT", "HARVEST"}:
        report.summary = (
            "KEEP baseline: Nova static fetch matches or beats library arms on fixture recall "
            "without browser ops cost. Crawl4AI/Crawlee remain HARVEST/REJECT for JS-only uplift."
        )
    else:
        report.summary = f"Highest fixture recall: {winner}. Review capability matrix before adoption."
    return report


def main() -> None:
    import json

    report = run_spike()
    print(json.dumps(report.as_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
