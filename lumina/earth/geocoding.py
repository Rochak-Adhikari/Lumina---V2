"""Lumina Earth P0.2 — Place-Search / Geocoding Adapter Contract.

Provider-neutral geocoding interface and Open-Meteo reference implementation.
Zero-budget, keyless, CC BY 4.0 terms.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Protocol

import aiohttp

DEFAULT_GEOCODING_ENDPOINT = 'https://geocoding-api.open-meteo.com/v1/search'
DEFAULT_TIMEOUT_SECONDS = 8.0
PROVIDER_NAME = 'open-meteo'
ATTRIBUTION_TEXT = 'Geocoding data by Open-Meteo.com / GeoNames (CC BY 4.0)'


class GeocodingError(Exception):
    """Base exception for geocoding adapter errors."""
    def __init__(self, message: str, code: str = 'geocoding_error'):
        super().__init__(message)
        self.code = code


class GeocodingValidationError(GeocodingError):
    """Raised when search query or parameters violate bounds."""
    def __init__(self, message: str):
        super().__init__(message, code='invalid_argument')


class GeocodingTimeoutError(GeocodingError):
    """Raised when geocoding request times out."""
    def __init__(self, message: str = 'Geocoding request timed out'):
        super().__init__(message, code='timeout')


class GeocodingHTTPError(GeocodingError):
    """Raised when provider returns an HTTP error code."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"HTTP {status_code}: {message}", code='provider_error')
        self.status_code = status_code


class GeocodingMalformedResponseError(GeocodingError):
    """Raised when geocoding response structure is unexpected."""
    def __init__(self, message: str):
        super().__init__(message, code='malformed_response')


class GeocodingProviderError(GeocodingError):
    """Raised when provider returns an explicit error payload."""
    def __init__(self, message: str):
        super().__init__(message, code='provider_error')


@dataclass(frozen=True)
class GeocodingCandidate:
    """Normalized candidate location returned from place search."""
    name: str
    latitude: float
    longitude: float
    country: str | None = None
    country_code: str | None = None
    admin1: str | None = None  # State / Province / Division
    admin2: str | None = None  # County / District
    elevation_m: float | None = None
    timezone: str | None = None
    provider_id: str | int | None = None
    provider: str = PROVIDER_NAME
    attribution: str = ATTRIBUTION_TEXT

    @property
    def display_context(self) -> str:
        """Construct user-readable geographic descriptor."""
        parts = [self.name]
        if self.admin1 and self.admin1 != self.name:
            parts.append(self.admin1)
        if self.country:
            parts.append(self.country)
        return ', '.join(parts)


@dataclass(frozen=True)
class GeocodingSearchResult:
    """Normalized place-search query result envelope."""
    query: str
    candidates: list[GeocodingCandidate] = field(default_factory=list)
    count: int = 0
    provider: str = PROVIDER_NAME
    retrieved_at: str = ''
    attribution: str = ATTRIBUTION_TEXT

    def to_dict(self) -> dict[str, Any]:
        """Convert result to JSON-serializable dictionary."""
        return {
            'ok': True,
            'status': 'success',
            'data': {
                'query': self.query,
                'count': self.count,
                'candidates': [
                    {
                        'name': c.name,
                        'display_name': c.display_context,
                        'latitude': c.latitude,
                        'longitude': c.longitude,
                        'country': c.country,
                        'country_code': c.country_code,
                        'admin1': c.admin1,
                        'admin2': c.admin2,
                        'elevation_m': c.elevation_m,
                        'timezone': c.timezone,
                        'provider_id': c.provider_id,
                    }
                    for c in self.candidates
                ],
            },
            'provenance': {
                'provider': self.provider,
                'retrieved_at': self.retrieved_at,
                'attribution': self.attribution,
            },
            'error': None,
        }


class GeocodingAdapter(Protocol):
    """Provider-neutral protocol for geographic place search."""

    async def search(
        self,
        query: str,
        limit: int = 5,
        language: str = 'en',
    ) -> GeocodingSearchResult:
        """Search places by text query, returning ranked candidates."""
        ...


def validate_search_query(query: Any, limit: Any) -> tuple[str, int]:
    """Validate and sanitize place query string and candidate limit."""
    if not isinstance(query, str):
        raise GeocodingValidationError(f"Query must be a string, received: {type(query).__name__}")

    stripped = query.strip()
    if not stripped:
        raise GeocodingValidationError("Place search query cannot be empty or whitespace only")

    if len(stripped) > 200:
        raise GeocodingValidationError(f"Place search query exceeds maximum length of 200 characters (length: {len(stripped)})")

    # Reject ASCII control characters except space and tab
    if any(ord(c) < 32 and c != '\t' for c in stripped):
        raise GeocodingValidationError("Place search query contains invalid control characters")

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise GeocodingValidationError(f"Limit must be an integer, received: {type(limit).__name__}")

    if not 1 <= limit <= 20:
        raise GeocodingValidationError(f"Limit must be between 1 and 20, received: {limit}")

    return stripped, limit


class OpenMeteoGeocodingAdapter:
    """Open-Meteo Geocoding API implementation of GeocodingAdapter."""

    def __init__(
        self,
        endpoint_url: str = DEFAULT_GEOCODING_ENDPOINT,
        session: aiohttp.ClientSession | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.endpoint_url = endpoint_url
        self._session = session
        self.timeout_seconds = timeout_seconds

    async def search(
        self,
        query: str,
        limit: int = 5,
        language: str = 'en',
    ) -> GeocodingSearchResult:
        """Query Open-Meteo Geocoding API and return normalized candidates."""
        clean_query, valid_limit = validate_search_query(query, limit)

        params: dict[str, str] = {
            'name': clean_query,
            'count': str(valid_limit),
            'language': language or 'en',
            'format': 'json',
        }

        headers = {
            'Accept': 'application/json',
            'User-Agent': 'LuminaEarth/0.2 (Open-Meteo CC BY 4.0; personal desktop assistant)',
        }

        retrieved_at = datetime.now(timezone.utc).isoformat()

        if self._session is not None:
            raw_data = await self._execute_request(self._session, params, headers)
        else:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout, trust_env=False) as temp_session:
                raw_data = await self._execute_request(temp_session, params, headers)

        return self._normalize_response(raw_data, clean_query, retrieved_at)

    async def _execute_request(
        self,
        session: aiohttp.ClientSession,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Execute async HTTP request."""
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with session.get(self.endpoint_url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception as exc:
                            raise GeocodingMalformedResponseError(f"Response is not valid JSON: {exc}") from exc
                        if not isinstance(data, dict):
                            raise GeocodingMalformedResponseError("Response JSON root must be an object")
                        if data.get('error'):
                            reason = data.get('reason', 'Provider returned unspecified error')
                            raise GeocodingProviderError(f"Open-Meteo Geocoding error: {reason}")
                        return data

                    try:
                        error_payload = await resp.json()
                        detail = error_payload.get('reason') if isinstance(error_payload, dict) else None
                    except Exception:
                        detail = None

                    message = detail or resp.reason or f"Request failed with status {resp.status}"
                    raise GeocodingHTTPError(resp.status, message)

        except asyncio.TimeoutError as exc:
            raise GeocodingTimeoutError(f"Open-Meteo geocoding request timed out after {self.timeout_seconds}s") from exc
        except aiohttp.ClientError as exc:
            raise GeocodingHTTPError(0, f"Network connection error: {exc}") from exc

    def _normalize_response(
        self,
        data: dict[str, Any],
        query: str,
        retrieved_at: str,
    ) -> GeocodingSearchResult:
        """Parse raw Open-Meteo geocoding response into normalized GeocodingSearchResult."""
        raw_results = data.get('results')
        if raw_results is None:
            # Open-Meteo returns {} or {'generationtime_ms': ...} when no places match
            return GeocodingSearchResult(
                query=query,
                candidates=[],
                count=0,
                provider=PROVIDER_NAME,
                retrieved_at=retrieved_at,
                attribution=ATTRIBUTION_TEXT,
            )

        if not isinstance(raw_results, list):
            raise GeocodingMalformedResponseError("Expected 'results' to be a list in geocoding response")

        candidates: list[GeocodingCandidate] = []

        def _opt_str(v: Any) -> str | None:
            return str(v).strip() if v is not None and str(v).strip() else None

        def _opt_float(v: Any) -> float | None:
            if v is None:
                return None
            try:
                f = float(v)
                return f if math.isfinite(f) else None
            except (ValueError, TypeError):
                return None

        for item in raw_results:
            if not isinstance(item, dict):
                continue

            name = item.get('name')
            if not isinstance(name, str) or not name.strip():
                continue

            lat_val = item.get('latitude')
            lon_val = item.get('longitude')
            try:
                lat = float(lat_val)
                lon = float(lon_val)
            except (TypeError, ValueError):
                continue

            # Validate coordinate range
            if not math.isfinite(lat) or not math.isfinite(lon):
                continue
            if not -90.0 <= lat <= 90.0 or not -180.0 <= lon <= 180.0:
                continue

            candidates.append(
                GeocodingCandidate(
                    name=name.strip(),
                    latitude=lat,
                    longitude=lon,
                    country=_opt_str(item.get('country')),
                    country_code=_opt_str(item.get('country_code')),
                    admin1=_opt_str(item.get('admin1')),
                    admin2=_opt_str(item.get('admin2')),
                    elevation_m=_opt_float(item.get('elevation')),
                    timezone=_opt_str(item.get('timezone')),
                    provider_id=item.get('id'),
                    provider=PROVIDER_NAME,
                    attribution=ATTRIBUTION_TEXT,
                )
            )

        return GeocodingSearchResult(
            query=query,
            candidates=candidates,
            count=len(candidates),
            provider=PROVIDER_NAME,
            retrieved_at=retrieved_at,
            attribution=ATTRIBUTION_TEXT,
        )
