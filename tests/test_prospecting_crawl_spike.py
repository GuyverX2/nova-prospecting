"""ARCH-W1-001 — Nova crawl three-way spike tests (hermetic fixtures only)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_FIXTURE = REPO_ROOT / "docs/architecture-program/wave-0-3/fixtures/crawl-cases.yaml"
HARNESS_FIXTURE = REPO_ROOT / "tools/crawl-spike/fixtures/crawl-cases.yaml"

sys.path.insert(0, str(REPO_ROOT / "tools/crawl-spike"))
sys.path.insert(0, str(REPO_ROOT / "services/api"))

from crawl_spike.capabilities import CAPABILITY_MATRIX, recommend_decision  # noqa: E402
from crawl_spike.harness import run_spike  # noqa: E402
from crawl_spike.providers.keep_nova import probe_ssrf  # noqa: E402

REQUIRED_DIMENSIONS = {
    "ssrf_safety",
    "robots_compliance",
    "provenance",
    "retries",
    "timeout",
    "structured_output",
    "js_rendering",
    "anti_bot_ops_cost",
    "tenant_isolation",
    "license",
    "integration_effort",
}

CASE_REQUIRED_FIELDS = {"id", "case_key", "ordinal", "title", "dimensions"}


def _load_fixture(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope="module")
def canonical_doc() -> dict:
    assert CANONICAL_FIXTURE.is_file(), f"missing fixture: {CANONICAL_FIXTURE}"
    return _load_fixture(CANONICAL_FIXTURE)


def test_fixture_files_exist_and_match():
    assert HARNESS_FIXTURE.is_file(), f"missing harness copy: {HARNESS_FIXTURE}"
    canonical = _load_fixture(CANONICAL_FIXTURE)
    harness = _load_fixture(HARNESS_FIXTURE)
    assert canonical["cases"] == harness["cases"]
    assert canonical["dimension_coverage"] == harness["dimension_coverage"]


def test_matrix_metadata(canonical_doc: dict):
    assert canonical_doc["task_id"] == "ARCH-W1-001"
    assert canonical_doc["spike_id"] == "SPIKE-CRAWL-001"
    assert canonical_doc["status"] == "ready"
    assert canonical_doc["baseline_arm"] == "keep_nova"
    assert set(canonical_doc["competitors"]) == {"crawl4ai", "crawlee"}
    assert set(canonical_doc["decision_options"]) == {"KEEP", "HARVEST", "INTEGRATE", "REJECT"}


def test_all_required_dimensions_covered(canonical_doc: dict):
    coverage = canonical_doc["dimension_coverage"]
    assert set(coverage) == REQUIRED_DIMENSIONS


def test_each_case_has_required_fields(canonical_doc: dict):
    for case in canonical_doc["cases"]:
        missing = CASE_REQUIRED_FIELDS - set(case)
        assert not missing, f"{case.get('id', '?')} missing fields: {missing}"


def test_ssrf_probes_block_unsafe_urls(canonical_doc: dict):
    for case in canonical_doc["cases"]:
        if not case.get("ssrf_probe"):
            continue
        result = probe_ssrf(case["url"])
        assert result.blocked, case["id"]
        allowed_codes = set(case.get("blocked_codes") or [])
        if allowed_codes:
            assert result.block_code in allowed_codes, case["id"]


def test_spike_harness_baseline_passes_static_case():
    report = run_spike()
    static = [
        item
        for item in report.case_results
        if item.case_id == "CRAWL-001" and item.arm == "keep_nova"
    ]
    assert static and static[0].passed


def test_spike_harness_js_gap_documented():
    report = run_spike()
    nova_js = next(
        item for item in report.case_results if item.case_id == "CRAWL-002" and item.arm == "keep_nova"
    )
    crawl4ai_js = next(
        item for item in report.case_results if item.case_id == "CRAWL-002" and item.arm == "crawl4ai"
    )
    assert not nova_js.passed
    assert crawl4ai_js.passed


def test_capability_matrix_covers_all_arms():
    assert set(CAPABILITY_MATRIX) == {"keep_nova", "crawl4ai", "crawlee"}
    for arm, caps in CAPABILITY_MATRIX.items():
        dims = {item.dimension for item in caps.scores}
        assert dims == REQUIRED_DIMENSIONS, arm


def test_recommended_decision_keep_baseline():
    report = run_spike()
    assert report.decisions["keep_nova"] == "KEEP"
    assert report.decisions["crawl4ai"] in {"HARVEST", "REJECT", "INTEGRATE"}
    assert report.decisions["crawlee"] in {"HARVEST", "REJECT", "INTEGRATE"}
    # Static HTML path: baseline should match library arms on fixture recall
    assert report.static_recall["keep_nova"] >= report.static_recall["crawl4ai"] - 0.05
    decisions = recommend_decision(
        extraction_recall=report.static_recall,
        capability_totals=report.capability_totals,
    )
    assert decisions["keep_nova"] == "KEEP"
