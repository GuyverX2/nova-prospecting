"""Versioned HTTP boundary for the SalesOS CRM."""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings


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

    def promote_prospect(self, *, bearer_token: str, tenant_id: str, prospect_id: str, payload: dict) -> CrmPromotion:
        if not self.base_url or not bearer_token:
            raise CrmUnavailable("SalesOS CRM is not configured")
        request = Request(
            f"{self.base_url}/api/{self.api_version}/nova/prospects/promote",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            method="POST",
            headers={"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json",
                     "Idempotency-Key": f"nova-prospect:{tenant_id}:{prospect_id}"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read(256_000).decode("utf-8"))
        except HTTPError as exc:
            raise CrmRejected(f"SalesOS CRM returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            raise CrmUnavailable("SalesOS CRM could not be reached") from exc
        try:
            return CrmPromotion(customer_id=str(body["customer_id"]), lead_id=str(body["lead_id"]),
                                case_id=str(body["case_id"]), already_promoted=bool(body.get("already_promoted")),
                                lead_path=str(body["crm_lead_path"]), case_path=str(body["crm_case_path"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise CrmRejected("SalesOS CRM returned an invalid promotion response") from exc
