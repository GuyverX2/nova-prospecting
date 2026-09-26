"""Fail-closed legacy SalesOS → standalone Nova identifier conversion."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class MappingError(ValueError):
    pass


_SUBJECT_FIELDS = {
    "prospecting_campaigns": (("created_by_user_id", "created_by_subject", False),),
    "website_prospects": (("assigned_user_id", "assigned_subject", True),),
    "website_analyses": (("requested_by_user_id", "requested_by_subject", False),),
    "website_proposals": (
        ("created_by_user_id", "created_by_subject", False),
        ("approved_by_user_id", "approved_by_subject", True),
    ),
    "prospecting_policies": (("updated_by_user_id", "updated_by_subject", False),),
    "prospect_suppressions": (("created_by_user_id", "created_by_subject", True),),
}


def _validated_mapping(mapping: Mapping[str, str], *, name: str) -> dict[str, str]:
    normalized = {str(key): str(value).strip() for key, value in mapping.items()}
    if not normalized or any(not key.strip() or not value for key, value in normalized.items()):
        raise MappingError(f"{name} must contain non-empty source and target identifiers")
    if len(set(normalized.values())) != len(normalized):
        raise MappingError(f"{name} must map each source identifier to a unique target identifier")
    return normalized


def map_legacy_row(
    table: str,
    row: Mapping[str, Any],
    *,
    tenant_ids: Mapping[str, str],
    user_subjects: Mapping[str, str],
) -> dict[str, Any]:
    """Convert one legacy row without writing it anywhere.

    Required ownership references must be explicitly mapped. Nullable user
    references remain null, but a non-null value never falls back to a default.
    """
    if table not in _SUBJECT_FIELDS:
        raise MappingError(f"unsupported Nova-owned table: {table}")
    if not row.get("id"):
        raise MappingError(f"{table}: stable id is required")

    tenants = _validated_mapping(tenant_ids, name="tenant_ids")
    subjects = _validated_mapping(user_subjects, name="user_subjects")
    source_tenant = str(row.get("tenant_id", ""))
    if source_tenant not in tenants:
        raise MappingError(f"{table}: no Nova tenant mapping for legacy tenant {source_tenant!r}")

    converted = dict(row)
    converted["tenant_id"] = tenants[source_tenant]
    for source_field, target_field, nullable in _SUBJECT_FIELDS[table]:
        source_value = row.get(source_field)
        converted.pop(source_field, None)
        if source_value is None and nullable:
            converted[target_field] = None
            continue
        source_user = str(source_value or "")
        if source_user not in subjects:
            raise MappingError(f"{table}: no Nova subject mapping for legacy user {source_user!r}")
        converted[target_field] = subjects[source_user]
    return converted
