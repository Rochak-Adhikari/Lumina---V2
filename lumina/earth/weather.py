"""Lumina Earth P0.2 — Open-Meteo Weather Adapter.

Zero-budget, keyless weather adapter adhering to Lumina architecture and
Open-Meteo CC BY 4.0 terms.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from typing import Any, Mapping

import aiohttp

DEFAULT_WEATHER_ENDPOINT = 'https://api.open-meteo.com/v1/forecast'
DEFAULT_TIMEOUT_SECONDS = 8.0
PROVIDER_NAME = 'open-meteo'
ATTRIBUTION_TEXT = 'Weather data by Open-Meteo.com (CC BY 4.0)'

# Official WMO 4677 Weather Code interpretation
WMO_WEATHER_CODES: Mapping[int, str] = {
    0: 'Clear sky',
    1: 'Mainly clear',
    2: 'Partly cloudy',
    3: 'Overcast',
    45: 'Fog',
    48: 'Depositing rime fog',
    51: 'Light drizzle',
    53: 'Moderate drizzle',
    55: 'Dense drizzle',
    56: 'Light freezing drizzle',
    57: 'Dense freezing drizzle',
    61: 'Slight rain',
    63: 'Moderate rain',
    65: 'Heavy rain',
    66: 'Light freezing rain',
    67: 'Heavy freezing rain',
    71: 'Slight snow fall',
    73: 'Moderate snow fall',
    75: 'Heavy snow fall',
    77: 'Snow grains',
    80: 'Slight rain showers',
    81: 'Moderate rain showers',
    82: 'Violent rain showers',
    85: 'Slight snow showers',
    86: 'Heavy snow showers',
    95: 'Thunderstorm',
    96: 'Thunderstorm with slight hail',
    99: 'Thunderstorm with heavy hail',
}


def interpret_weather_code(code: int | None) -> str:
    """Map WMO code to human-readable weather description."""
    if code is None:
        return 'Unknown weather condition'
    return WMO_WEATHER_CODES.get(code, f'Weather code {code}')


class WeatherError(Exception):
    """Base exception for all Lumina Earth weather adapter errors."""
    def __init__(self, message: str, code: str = 'weather_error'):
        super().__init__(message)
        self.code = code


class WeatherValidationError(WeatherError):
    """Raised when coordinates or request parameters are invalid."""
    def __init__(self, message: str):
        super().__init__(message, code='invalid_argument')


class WeatherTimeoutError(WeatherError):
    """Raised when weather request times out."""
    def __init__(self, message: str = 'Weather request timed out'):
        super().__init__(message, code='timeout')


class WeatherHTTPError(WeatherError):
    """Raised when weather provider returns an HTTP error."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"HTTP {status_code}: {message}", code='provider_error')
        self.status_code = status_code


class WeatherMalformedResponseError(WeatherError):
    """Raised when weather response schema is unexpected or malformed."""
    def __init__(self, message: str):
        super().__init__(message, code='malformed_response')


class WeatherProviderError(WeatherError):
    """Raised when provider indicates an error payload."""
    def __init__(self, message: str):
        super().__init__(message, code='provider_error')


@dataclass(frozen=True)
class CurrentWeather:
    """Normalized snapshot of current meteorological conditions."""
    temperature: float
    apparent_temperature: float | None
    humidity_relative: float | None
    precipitation: float | None
    weather_code: int | None
    weather_description: str
    wind_speed: float | None
    wind_direction: float | None
    is_day: bool | None
    timestamp_iso: str
    units: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyForecastDay:
    """Normalized day forecast."""
    date: str  # YYYY-MM-DD
    weather_code: int | None
    weather_description: str
    temperature_max: float | None
    temperature_min: float | None
    precipitation_sum: float | None


@dataclass(frozen=True)
class WeatherReport:
    """Normalized complete weather response contract."""
    latitude: float
    longitude: float
    elevation_m: float | None
    timezone_name: str
    current: CurrentWeather
    daily: list[DailyForecastDay]
    units: dict[str, str]
    provider: str
    retrieved_at: str
    attribution: str

    def to_dict(self) -> dict[str, Any]:
        """Convert report to JSON-serializable dictionary."""
        return {
            'ok': True,
            'status': 'success',
            'data': {
                'location': {
                    'latitude': self.latitude,
                    'longitude': self.longitude,
                    'elevation_m': self.elevation_m,
                    'timezone': self.timezone_name,
                },
                'current': {
                    'temperature': self.current.temperature,
                    'apparent_temperature': self.current.apparent_temperature,
                    'humidity_relative': self.current.humidity_relative,
                    'precipitation': self.current.precipitation,
                    'weather_code': self.current.weather_code,
                    'weather_description': self.current.weather_description,
                    'wind_speed': self.current.wind_speed,
                    'wind_direction': self.current.wind_direction,
                    'is_day': self.current.is_day,
                    'timestamp': self.current.timestamp_iso,
                    'units': self.current.units,
                },
                'daily': [
                    {
                        'date': d.date,
                        'weather_code': d.weather_code,
                        'weather_description': d.weather_description,
                        'temperature_max': d.temperature_max,
                        'temperature_min': d.temperature_min,
                        'precipitation_sum': d.precipitation_sum,
                    }
                    for d in self.daily
                ],
                'units': self.units,
            },
            'provenance': {
                'provider': self.provider,
                'retrieved_at': self.retrieved_at,
                'attribution': self.attribution,
            },
            'error': None,
        }


def validate_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
    """Validate latitude and longitude, rejecting non-finite numbers and out-of-range values."""
    if not isinstance(latitude, (int, float)) or isinstance(latitude, bool):
        raise WeatherValidationError(f"Latitude must be a numeric value, received: {type(latitude).__name__}")
    if not isinstance(longitude, (int, float)) or isinstance(longitude, bool):
        raise WeatherValidationError(f"Longitude must be a numeric value, received: {type(longitude).__name__}")

    lat = float(latitude)
    lon = float(longitude)

    if not math.isfinite(lat):
        raise WeatherValidationError(f"Latitude must be a finite number, received: {lat}")
    if not math.isfinite(lon):
        raise WeatherValidationError(f"Longitude must be a finite number, received: {lon}")

    if not -90.0 <= lat <= 90.0:
        raise WeatherValidationError(f"Latitude must be between -90 and +90 degrees, received: {lat}")
    if not -180.0 <= lon <= 180.0:
        raise WeatherValidationError(f"Longitude must be between -180 and +180 degrees, received: {lon}")

    return lat, lon


def validate_units(units: str) -> str:
    """Validate unit system."""
    if not isinstance(units, str):
        raise WeatherValidationError(f"Units must be a string ('metric' or 'imperial'), received: {type(units).__name__}")
    norm = units.strip().lower()
    if norm not in {'metric', 'imperial'}:
        raise WeatherValidationError(f"Unsupported units '{units}'. Must be 'metric' or 'imperial'.")
    return norm


class OpenMeteoWeatherAdapter:
    """Zero-budget weather adapter querying the public Open-Meteo forecast API."""

    def __init__(
        self,
        endpoint_url: str = DEFAULT_WEATHER_ENDPOINT,
        session: aiohttp.ClientSession | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.endpoint_url = endpoint_url
        self._session = session
        self.timeout_seconds = timeout_seconds

    async def get_weather(
        self,
        latitude: float,
        longitude: float,
        units: str = 'metric',
        forecast_days: int = 7,
    ) -> WeatherReport:
        """Fetch and normalize weather for validated geographic coordinates."""
        lat, lon = validate_coordinates(latitude, longitude)
        unit_system = validate_units(units)

        if not isinstance(forecast_days, int) or isinstance(forecast_days, bool) or not 1 <= forecast_days <= 16:
            raise WeatherValidationError(f"forecast_days must be an integer between 1 and 16, received: {forecast_days}")

        params: dict[str, str] = {
            'latitude': f"{lat:.6f}",
            'longitude': f"{lon:.6f}",
            'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m,wind_direction_10m,is_day',
            'daily': 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum',
            'forecast_days': str(forecast_days),
            'timezone': 'auto',
        }

        if unit_system == 'imperial':
            params['temperature_unit'] = 'fahrenheit'
            params['wind_speed_unit'] = 'mph'
            params['precipitation_unit'] = 'inch'

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

        return self._normalize_response(raw_data, lat, lon, retrieved_at)

    async def _execute_request(
        self,
        session: aiohttp.ClientSession,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        """Perform HTTP request with timeout and error handling."""
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with session.get(self.endpoint_url, params=params, headers=headers) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json()
                        except Exception as exc:
                            raise WeatherMalformedResponseError(f"Response is not valid JSON: {exc}") from exc
                        if not isinstance(data, dict):
                            raise WeatherMalformedResponseError("Response JSON root must be an object")
                        if data.get('error'):
                            reason = data.get('reason', 'Provider returned unspecified error')
                            raise WeatherProviderError(f"Open-Meteo error: {reason}")
                        return data

                    # Handle error status codes
                    try:
                        error_payload = await resp.json()
                        detail = error_payload.get('reason') if isinstance(error_payload, dict) else None
                    except Exception:
                        detail = None

                    message = detail or resp.reason or f"Request failed with status {resp.status}"
                    raise WeatherHTTPError(resp.status, message)

        except asyncio.TimeoutError as exc:
            raise WeatherTimeoutError(f"Open-Meteo weather request timed out after {self.timeout_seconds}s") from exc
        except aiohttp.ClientError as exc:
            raise WeatherHTTPError(0, f"Network connection error: {exc}") from exc

    def _normalize_response(
        self,
        data: dict[str, Any],
        req_lat: float,
        req_lon: float,
        retrieved_at: str,
    ) -> WeatherReport:
        """Parse raw Open-Meteo response into normalized WeatherReport."""
        current_raw = data.get('current')
        if not isinstance(current_raw, dict):
            raise WeatherMalformedResponseError("Missing or invalid 'current' weather block in response")

        current_units = data.get('current_units', {}) if isinstance(data.get('current_units'), dict) else {}
        daily_units = data.get('daily_units', {}) if isinstance(data.get('daily_units'), dict) else {}

        merged_units: dict[str, str] = {
            'temperature': current_units.get('temperature_2m', '°C'),
            'apparent_temperature': current_units.get('apparent_temperature', '°C'),
            'relative_humidity': current_units.get('relative_humidity_2m', '%'),
            'precipitation': current_units.get('precipitation', 'mm'),
            'wind_speed': current_units.get('wind_speed_10m', 'km/h'),
            'wind_direction': current_units.get('wind_direction_10m', '°'),
            'precipitation_sum': daily_units.get('precipitation_sum', 'mm'),
        }

        try:
            temp = float(current_raw['temperature_2m'])
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherMalformedResponseError(f"Missing mandatory current temperature_2m: {exc}") from exc

        weather_code = current_raw.get('weather_code')
        if weather_code is not None:
            try:
                weather_code = int(weather_code)
            except (ValueError, TypeError):
                weather_code = None

        weather_desc = interpret_weather_code(weather_code)

        def _opt_float(val: Any) -> float | None:
            if val is None:
                return None
            try:
                f = float(val)
                return f if math.isfinite(f) else None
            except (ValueError, TypeError):
                return None

        is_day_val = current_raw.get('is_day')
        is_day = bool(is_day_val) if is_day_val in (0, 1) else None

        current = CurrentWeather(
            temperature=temp,
            apparent_temperature=_opt_float(current_raw.get('apparent_temperature')),
            humidity_relative=_opt_float(current_raw.get('relative_humidity_2m')),
            precipitation=_opt_float(current_raw.get('precipitation')),
            weather_code=weather_code,
            weather_description=weather_desc,
            wind_speed=_opt_float(current_raw.get('wind_speed_10m')),
            wind_direction=_opt_float(current_raw.get('wind_direction_10m')),
            is_day=is_day,
            timestamp_iso=str(current_raw.get('time', retrieved_at)),
            units=merged_units,
        )

        daily_list: list[DailyForecastDay] = []
        daily_raw = data.get('daily')
        if isinstance(daily_raw, dict):
            times = daily_raw.get('time', [])
            codes = daily_raw.get('weather_code', [])
            t_max = daily_raw.get('temperature_2m_max', [])
            t_min = daily_raw.get('temperature_2m_min', [])
            p_sum = daily_raw.get('precipitation_sum', [])

            if isinstance(times, list):
                for i, date_str in enumerate(times):
                    if not isinstance(date_str, str):
                        continue
                    code_val = codes[i] if i < len(codes) else None
                    code_int = None
                    if code_val is not None:
                        try:
                            code_int = int(code_val)
                        except (ValueError, TypeError):
                            code_int = None

                    daily_list.append(
                        DailyForecastDay(
                            date=date_str,
                            weather_code=code_int,
                            weather_description=interpret_weather_code(code_int),
                            temperature_max=_opt_float(t_max[i]) if i < len(t_max) else None,
                            temperature_min=_opt_float(t_min[i]) if i < len(t_min) else None,
                            precipitation_sum=_opt_float(p_sum[i]) if i < len(p_sum) else None,
                        )
                    )

        resp_lat = _opt_float(data.get('latitude')) or req_lat
        resp_lon = _opt_float(data.get('longitude')) or req_lon
        elevation = _opt_float(data.get('elevation'))
        tz_name = str(data.get('timezone', 'UTC'))

        return WeatherReport(
            latitude=resp_lat,
            longitude=resp_lon,
            elevation_m=elevation,
            timezone_name=tz_name,
            current=current,
            daily=daily_list,
            units=merged_units,
            provider=PROVIDER_NAME,
            retrieved_at=retrieved_at,
            attribution=ATTRIBUTION_TEXT,
        )
