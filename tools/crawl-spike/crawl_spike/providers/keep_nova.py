"""Arm A — existing SalesOS Nova prospecting fetch + extract (baseline)."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.prospecting.agentic_extract import extract_facts
from app.prospecting.analyzer import WebsiteAuditError, analyze_html, normalize_public_url


@dataclass
class NovaArmResult:
    arm: str = "keep_nova"
    audit: dict = field(default_factory=dict)
    facts: list[dict] = field(default_factory=list)
    blocked: bool = False
    block_code: str | None = None
    provenance: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "arm": self.arm,
            "audit": self.audit,
            "facts": self.facts,
            "blocked": self.blocked,
            "block_code": self.block_code,
            "provenance": self.provenance,
        }


def probe_ssrf(url: str) -> NovaArmResult:
    result = NovaArmResult()
    try:
        normalize_public_url(url)
    except WebsiteAuditError as exc:
        result.blocked = True
        result.block_code = exc.code
        return result
    result.blocked = False
    return result


def extract_from_html(*, html: str, url: str) -> NovaArmResult:
    audit = analyze_html(html, url, final_url=url, fetch_duration_ms=0)
    facts = extract_facts(html)
    return NovaArmResult(
        audit=audit,
        facts=[{"field": f.field, "value": f.value, "confidence": f.confidence} for f in facts],
        provenance={
            "snapshot_sha256": audit.get("snapshot_sha256"),
            "scope": audit.get("technical", {}).get("scope"),
            "limitations": audit.get("technical", {}).get("limitations", []),
            "provider": "analyzer.fetch_public_html + agentic_extract",
        },
    )
