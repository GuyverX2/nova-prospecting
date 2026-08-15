"""Explicit, configurable company discovery providers.

No provider runs unless configured by an operator. Google Places is supported
because it offers a documented API; HTML scraping of directory sites is not.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.config import settings

GOOGLE_PLACES_ENDPOINT = "https://places.googleapis.com/v1/places:searchText"


class DiscoveryProviderError(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 422):
        self.code = code
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


@dataclass(frozen=True)
class DiscoveredCompany:
    company_name: str
    website_url: str | None
    city: str | None
    industry: str | None
    source_url: str
    source_id: str
    phone: str | None = None


def provider_status() -> dict:
    provider = settings.PROSPECTING_DISCOVERY_PROVIDER
    return {
        "discovery": {
            "provider": provider,
            "configured": provider == "google_places" and bool(settings.GOOGLE_PLACES_API_KEY),
            "supported": ["manual", "google_places"],
            "scrapes_directories": False,
        },
        "website_fetch": {
            "enabled": settings.PROSPECTING_FETCH_ENABLED,
            "robots_respected": True,
            "private_networks_blocked": True,
            "max_page_bytes": 1_500_000,
            "pagespeed_configured": bool(settings.PAGESPEED_API_KEY),
        },
        "email": {
            "provider": settings.PROSPECTING_EMAIL_PROVIDER,
            "real_send_enabled": settings.PROSPECTING_REAL_EMAIL_ENABLED,
            "configured": bool(settings.PROSPECTING_EMAIL_API_KEY and settings.PROSPECTING_EMAIL_FROM),
        },
    }


def discover_companies(query: str, region: str | None, limit: int) -> list[DiscoveredCompany]:
    provider = settings.PROSPECTING_DISCOVERY_PROVIDER
    if provider == "disabled":
        raise DiscoveryProviderError(
            "DISCOVERY_PROVIDER_DISABLED",
            "Company discovery is disabled. Use manual/CSV intake or configure a documented provider.",
            409,
        )
    if provider != "google_places":
        raise DiscoveryProviderError("DISCOVERY_PROVIDER_UNSUPPORTED", f"Unsupported discovery provider: {provider}")
    return _google_places(query, region, limit)


def _google_places(query: str, region: str | None, limit: int) -> list[DiscoveredCompany]:
    if not settings.GOOGLE_PLACES_API_KEY:
        raise DiscoveryProviderError("DISCOVERY_PROVIDER_NOT_CONFIGURED", "Google Places API key is not configured", 409)
    text_query = f"{query} {region or ''}".strip()
    body = json.dumps({"textQuery": text_query, "languageCode": "sv", "regionCode": "SE", "maxResultCount": limit}).encode("utf-8")
    request = Request(
        GOOGLE_PLACES_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.GOOGLE_PLACES_API_KEY,
            "X-Goog-FieldMask": "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.primaryTypeDisplayName,places.nationalPhoneNumber",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            payload = json.loads(response.read(1_000_000).decode("utf-8"))
    except HTTPError as exc:
        raise DiscoveryProviderError("DISCOVERY_UPSTREAM_ERROR", f"Discovery provider returned HTTP {exc.code}", 502) from exc
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        raise DiscoveryProviderError("DISCOVERY_UPSTREAM_UNAVAILABLE", "Discovery provider could not be reached", 502) from exc
    items: list[DiscoveredCompany] = []
    for place in payload.get("places", [])[:limit]:
        source_id = str(place.get("id") or "").strip()
        name = str((place.get("displayName") or {}).get("text") or "").strip()
        if not source_id or not name:
            continue
        address = str(place.get("formattedAddress") or "").strip()
        city = _city_from_address(address)
        items.append(
            DiscoveredCompany(
                company_name=name,
                website_url=(str(place.get("websiteUri") or "").strip() or None),
                city=city,
                industry=(str((place.get("primaryTypeDisplayName") or {}).get("text") or "").strip() or None),
                phone=(str(place.get("nationalPhoneNumber") or "").strip() or None),
                source_id=source_id,
                source_url=f"https://www.google.com/maps/place/?q=place_id:{source_id}",
            )
        )
    return items


def _city_from_address(address: str) -> str | None:
    parts = [part.strip() for part in address.split(",") if part.strip()]
    if len(parts) < 2:
        return None
    candidate = parts[-2]
    candidate = " ".join(piece for piece in candidate.split() if not piece.isdigit())
    return candidate or None
