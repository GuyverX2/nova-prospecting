"""Versioned HTTP boundary for the SalesOS CRM."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings
from app.integrations.http import (
    IntegrationRejected,
    IntegrationUnavailable,
    RetryPolicy,
    request_json,
)


class CrmUnavailable(Exception):
    pass


class CrmRejected(Exception):
    pass


@dataclass(frozen=True)
class CrmPromotion:
    customer_id: str
    lead_id: str
    case_id: str
    already_promoted: bool
    lead_path: str
    case_path: str


class SalesOSCrmClient:
    api_version = "v1"

    def __init__(self, base_url: str | None = None, timeout: float | None = None):
        self.base_url = (base_url if base_url is not None else settings.SALESOS_CRM_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.SALESOS_CRM_TIMEOUT_SECONDS

    def promote_prospect(
        self, *, bearer_token: str, tenant_id: str, prospect_id: str, payload: dict
    ) -> CrmPromotion:
        if not self.base_url or not bearer_token:
            raise CrmUnavailable("SalesOS CRM is not configured")
        try:
            body = request_json(
                f"{self.base_url}/api/{self.api_version}/nova/prospects/promote",
                method="POST",
                json_body=payload,
                headers={
                    "Authorization": f"Bearer {bearer_token}",
                    "Idempotency-Key": f"nova-prospect:{tenant_id}:{prospect_id}",
                },
                timeout=self.timeout,
                max_bytes=256_000,
                # The stable idempotency key makes a repeat safe: the CRM
                # returns the first promotion instead of creating a second.
                retry=RetryPolicy(attempts=3),
                provider="SalesOS CRM",
            )
        except IntegrationRejected as exc:
            raise CrmRejected(str(exc)) from exc
        except IntegrationUnavailable as exc:
            raise CrmUnavailable("SalesOS CRM could not be reached") from exc
        try:
            return CrmPromotion(
                customer_id=str(body["customer_id"]),
                lead_id=str(body["lead_id"]),
                case_id=str(body["case_id"]),
                already_promoted=bool(body.get("already_promoted")),
                lead_path=str(body["crm_lead_path"]),
                case_path=str(body["crm_case_path"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CrmRejected("SalesOS CRM returned an invalid promotion response") from exc
