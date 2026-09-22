"""Tenant context derived from a verified platform bearer token."""
from dataclasses import dataclass

from sqlalchemy import Column, Integer, String, Text

from app.db.session import Base
@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    roles: frozenset[str]
    scopes: frozenset[str]

    def can_write(self) -> bool:
        return "nova:write" in self.scopes or "platform_admin" in self.roles


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    actor_subject = Column(String(255), nullable=False)
    action_type = Column(String(160), nullable=False)
    target_type = Column(String(120), nullable=False)
    target_id = Column(String(120), nullable=False)
    request_id = Column(String(120), nullable=True)
    after_json = Column(Text, nullable=True)


def record_audit(db, *, tenant_id, actor_subject, action_type, target_type, target_id, request_id, after=None, **_):
    import json

    db.add(AuditEvent(tenant_id=tenant_id, actor_subject=actor_subject, action_type=action_type,
                      target_type=target_type, target_id=target_id, request_id=request_id,
                      after_json=json.dumps(after or {}, separators=(",", ":"))))
