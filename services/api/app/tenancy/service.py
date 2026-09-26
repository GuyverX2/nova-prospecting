"""Tenant context derived from a verified platform bearer token."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.sql import func

from app.db.session import Base

WRITE_SCOPE = "nova:write"
ADMIN_ROLE = "platform_admin"

#: Audit payloads are compact by policy: they justify a change, they are not a
#: copy of the record. The cap also stops an operator-supplied field from
#: turning the audit trail into unbounded storage.
MAX_AUDIT_PAYLOAD_CHARS = 4000


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]

    def can_write(self) -> bool:
        return WRITE_SCOPE in self.scopes or ADMIN_ROLE in self.roles


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_event_tenant_created", "tenant_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    actor_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_id: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    after_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


def record_audit(
    db: Session,
    *,
    tenant_id: str,
    actor_subject: str,
    action_type: str,
    target_type: str,
    target_id: str,
    request_id: str | None = None,
    after: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append a tenant-scoped audit event to the current transaction.

    The caller owns the commit: an audit row is written only if the change it
    describes is also committed.
    """
    payload = json.dumps(after or {}, separators=(",", ":"), ensure_ascii=False, default=str)
    if len(payload) > MAX_AUDIT_PAYLOAD_CHARS:
        payload = json.dumps({"truncated": True, "chars": len(payload)}, separators=(",", ":"))
    event = AuditEvent(
        tenant_id=tenant_id,
        actor_subject=actor_subject,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id,
        request_id=request_id,
        after_json=payload,
    )
    db.add(event)
    return event
