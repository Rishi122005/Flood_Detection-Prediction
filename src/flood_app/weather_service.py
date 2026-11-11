"""Open-Meteo weather retrieval and transparent rainfall screening rules."""

from __future__ import annotations

import copy
import json
import math
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TIMEZONE = "Asia/Kolkata"
WEATHER_TZ = ZoneInfo(WEATHER_TIMEZONE)

INDIA_LOCATIONS = (
    {"id": "guwahati", "name": "Guwahati, Assam", "latitude": 26.1445, "longitude": 91.7362},
    {"id": "patna", "name": "Patna, Bihar", "latitude": 25.5941, "longitude": 85.1376},
    {"id": "bhubaneswar", "name": "Bhubaneswar, Odisha", "latitude": 20.2961, "longitude": 85.8245},
    {"id": "chennai", "name": "Chennai, Tamil Nadu", "latitude": 13.0827, "longitude": 80.2707},
    {"id": "kochi", "name": "Kochi, Kerala", "latitude": 9.9312, "longitude": 76.2673},
    {"id": "mumbai", "name": "Mumbai, Maharashtra", "latitude": 19.0760, "longitude": 72.8777},
    {"id": "kolkata", "name": "Kolkata, West Bengal", "latitude": 22.5726, "longitude": 88.3639},
    {"id": "delhi", "name": "Delhi", "latitude": 28.6139, "longitude": 77.2090},
    {"id": "hyderabad", "name": "Hyderabad, Telangana", "latitude": 17.3850, "longitude": 78.4867},
    {"id": "bengaluru", "name": "Bengaluru, Karnataka", "latitude": 12.9716, "longitude": 77.5946},
)
_LOCATIONS_BY_ID = {item["id"]: item for item in INDIA_LOCATIONS}


@dataclass(frozen=True)
class RainfallThresholds:
    """Prototype screening thresholds in mm and precipitation probability percent."""

    moderate_3h_mm: float = 15.0
    moderate_24h_mm: float = 50.0
    moderate_hourly_mm: float = 15.0
    moderate_hourly_probability_pct: float = 50.0
    high_3h_mm: float = 50.0
    high_24h_mm: float = 100.0
    high_hourly_mm: float = 30.0
    high_hourly_probability_pct: float = 60.0


DEFAULT_THRESHOLDS = RainfallThresholds()

_WMO_CONDITIONS = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain", 66: "Light freezing rain",
    67: "Heavy freezing rain", 71: "Slight snowfall", 73: "Moderate snowfall",
    75: "Heavy snowfall", 77: "Snow grains", 80: "Slight rain showers",
    81: "Moderate rain showers", 82: "Violent rain showers", 85: "Slight snow showers",
    86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


class WeatherServiceError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    if not math.isfinite(latitude):
        raise ValueError("latitude must be finite")
    if not -90 <= latitude <= 90:
        raise ValueError("latitude must be between -90 and 90")
    if not math.isfinite(longitude):
        raise ValueError("longitude must be finite")
    if not -180 <= longitude <= 180:
        raise ValueError("longitude must be between -180 and 180")
    return float(latitude), float(longitude)


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _parse_local_time(value: str, timezone_name: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except ZoneInfoNotFoundError as exc:
            raise WeatherServiceError("Weather response contained an unknown timezone") from exc
    return parsed


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return radius_km * 2 * math.asin(min(1.0, math.sqrt(value)))


def assess_rainfall_risk(next_3h_mm: float | None, next_24h_mm: float | None,
                         max_hourly_mm: float | None, max_probability_pct: float | None,
                         valid_hour_count: int, thresholds: RainfallThresholds = DEFAULT_THRESHOLDS,
                         probability_at_max_hourly_pct: float | None = None) -> dict:
    """Classify rainfall conditions only; this is not flood probability or a warning."""
    if probability_at_max_hourly_pct is None:
        probability_at_max_hourly_pct = max_probability_pct
    inputs = (next_3h_mm, next_24h_mm, max_hourly_mm, max_probability_pct,
              probability_at_max_hourly_pct)
    if valid_hour_count < 24 or any(_finite_number(value) is None for value in inputs):
        return {
            "status": "insufficient_data", "level": None,
            "message": "Insufficient weather data for risk assessment.",
            "reasons": ["A complete next-24-hour precipitation and probability forecast is required."],
            "thresholds": asdict(thresholds),
        }

    p3, p24, hourly, probability, peak_probability = (float(value) for value in inputs)
    high_reasons = []
    if p3 >= thresholds.high_3h_mm:
        high_reasons.append(f"Next-3-hour rainfall {p3:.1f} mm meets the HIGH screening threshold (≥ {thresholds.high_3h_mm:g} mm).")
    if p24 >= thresholds.high_24h_mm:
        high_reasons.append(f"Next-24-hour rainfall {p24:.1f} mm meets the HIGH screening threshold (≥ {thresholds.high_24h_mm:g} mm).")
    if hourly >= thresholds.high_hourly_mm and peak_probability >= thresholds.high_hourly_probability_pct:
        high_reasons.append(
            f"Maximum hourly rainfall {hourly:.1f} mm meets ≥ {thresholds.high_hourly_mm:g} mm/h and precipitation probability in that same hour ({peak_probability:.0f}%) meets ≥ {thresholds.high_hourly_probability_pct:g}%."
        )
    moderate_reasons = []
    if p3 >= thresholds.moderate_3h_mm:
        moderate_reasons.append(f"Next-3-hour rainfall {p3:.1f} mm meets the MODERATE screening threshold (≥ {thresholds.moderate_3h_mm:g} mm).")
    if p24 >= thresholds.moderate_24h_mm:
        moderate_reasons.append(f"Next-24-hour rainfall {p24:.1f} mm meets the MODERATE screening threshold (≥ {thresholds.moderate_24h_mm:g} mm).")
    if hourly >= thresholds.moderate_hourly_mm and peak_probability >= thresholds.moderate_hourly_probability_pct:
        moderate_reasons.append(
            f"Maximum hourly rainfall {hourly:.1f} mm/h meets ≥ {thresholds.moderate_hourly_mm:g} mm/h and precipitation probability in that same hour ({peak_probability:.0f}%) meets ≥ {thresholds.moderate_hourly_probability_pct:g}%.")

    if high_reasons:
        level, reasons = "HIGH", high_reasons
    elif moderate_reasons:
        level, reasons = "MODERATE", moderate_reasons
    else:
        level = "LOW"
        reasons = ["Complete forecast values remain below the configured MODERATE rainfall-screening conditions."]
    reasons.append(f"Maximum precipitation probability is {probability:.0f}%; this is chance of precipitation, not flood probability.")
    return {"status": "available", "level": level, "message": f"{level} rainfall-based screening",
            "reasons": reasons, "thresholds": asdict(thresholds), "valid_hour_count": valid_hour_count}


def _open_meteo_json(url: str, timeout: float) -> dict:
    request = Request(url, headers={"User-Agent": "FloodMonitoring-Demo/1.0 (Open-Meteo free forecast API)"})
    try:
        with urlopen(request, timeout=timeout) as response:
            if response.status != 200:
                raise WeatherServiceError(f"Open-Meteo returned HTTP {response.status}")
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise WeatherServiceError(f"Open-Meteo returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WeatherServiceError(f"Could not retrieve Open-Meteo forecast: {exc}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WeatherServiceError("Open-Meteo returned an unreadable forecast response") from exc


def _weather_code_description(code: Any) -> str:
    number = _finite_number(code)
    return _WMO_CONDITIONS.get(int(number), "Weather condition unavailable") if number is not None else "Weather condition unavailable"


def build_weather_result(raw: dict, latitude: float, longitude: float, location_name: str,
                         retrieved_at: str | None = None) -> dict:
    """Normalize an Open-Meteo response and calculate its next-3h/24h values."""
    latitude, longitude = validate_coordinates(latitude, longitude)
    if not isinstance(raw, dict) or raw.get("error"):
        detail = raw.get("reason", "weather forecast response is empty") if isinstance(raw, dict) else "weather forecast response is empty"
        raise WeatherServiceError(f"Open-Meteo forecast unavailable: {detail}")
    hourly = raw.get("hourly") if isinstance(raw.get("hourly"), dict) else {}
    times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    if not times:
        raise WeatherServiceError("Open-Meteo returned no hourly forecast timestamps")
    timezone_name = raw.get("timezone") or WEATHER_TIMEZONE
    current = raw.get("current") if isinstance(raw.get("current"), dict) else {}
    current_time_raw = current.get("time")
    try:
        current_time = _parse_local_time(current_time_raw, timezone_name) if current_time_raw else datetime.now(ZoneInfo(timezone_name))
        forecast_times = [_parse_local_time(str(value), timezone_name) for value in times]
    except (ValueError, TypeError) as exc:
        raise WeatherServiceError("Open-Meteo returned invalid forecast timestamps") from exc

    keys = ("precipitation", "precipitation_probability", "temperature_2m", "relative_humidity_2m", "wind_speed_10m", "weather_code")
    arrays = {key: hourly.get(key) if isinstance(hourly.get(key), list) else [] for key in keys}
    future_indices = [index for index, stamp in enumerate(forecast_times) if stamp > current_time]
    future_indices = future_indices[:24]
    forecast_rows = []
    for index in future_indices:
        stamp = forecast_times[index]
        row = {"time": stamp.isoformat(timespec="minutes")}
        for key, output_key in (("precipitation", "precipitation_mm"),
                                ("precipitation_probability", "precipitation_probability_pct"),
                                ("temperature_2m", "temperature_2m_c"),
                                ("relative_humidity_2m", "relative_humidity_pct"),
                                ("wind_speed_10m", "wind_speed_10m_kmh")):
            values = arrays[key]
            row[output_key] = _finite_number(values[index]) if index < len(values) else None
        code_values = arrays["weather_code"]
        code = _finite_number(code_values[index]) if index < len(code_values) else None
        row["weather_code"] = int(code) if code is not None else None
        row["weather_condition"] = _weather_code_description(code)
        forecast_rows.append(row)

    precip = [row["precipitation_mm"] for row in forecast_rows]
    probability = [row["precipitation_probability_pct"] for row in forecast_rows]
    complete_precip = len(forecast_rows) >= 24 and all(value is not None for value in precip)
    complete_probability = len(forecast_rows) >= 24 and all(value is not None for value in probability)
    next_3h = sum(precip[:3]) if len(precip) >= 3 and all(value is not None for value in precip[:3]) else None
    next_24h = sum(precip) if complete_precip else None
    max_hourly = max(precip) if complete_precip else None
    max_probability = max(probability) if complete_probability else None
    peak_index = precip.index(max_hourly) if max_hourly is not None else None
    probability_at_peak = probability[peak_index] if peak_index is not None else None
    valid_count = 24 if complete_precip and complete_probability else min(
        sum(value is not None for value in precip), sum(value is not None for value in probability))
    screening = assess_rainfall_risk(next_3h, next_24h, max_hourly, max_probability, valid_count,
                                     probability_at_max_hourly_pct=probability_at_peak)

    current_values = {
        "temperature_2m_c": _finite_number(current.get("temperature_2m")),
        "relative_humidity_pct": _finite_number(current.get("relative_humidity_2m")),
        "wind_speed_10m_kmh": _finite_number(current.get("wind_speed_10m")),
        "weather_code": current.get("weather_code"),
    }
    current_code = current_values["weather_code"]
    current_values["weather_condition"] = _weather_code_description(current_code)
    grid_lat = _finite_number(raw.get("latitude"))
    grid_lon = _finite_number(raw.get("longitude"))
    grid = {"latitude": grid_lat, "longitude": grid_lon, "elevation_m": _finite_number(raw.get("elevation")),
            "distance_from_selected_km": _haversine_km(latitude, longitude, grid_lat, grid_lon) if grid_lat is not None and grid_lon is not None else None}
    return {
        "status": "ok", "location": {"name": location_name, "selected_latitude": latitude, "selected_longitude": longitude,
                                      "weather_grid": grid},
        "timezone": timezone_name, "current_time": current_time.isoformat(timespec="minutes"),
        "current_weather": current_values,
        "rainfall": {"next_3h_mm": next_3h, "next_24h_mm": next_24h,
                     "maximum_hourly_mm": max_hourly, "maximum_precipitation_probability_pct": max_probability,
                     "probability_at_maximum_hourly_rainfall_pct": probability_at_peak,
                     "complete_24h_precipitation": complete_precip, "complete_24h_probability": complete_probability},
        "hourly_forecast_next_24h": forecast_rows,
        "risk_assessment": screening,
        "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"provider": "Open-Meteo", "url": OPEN_METEO_URL, "attribution": "Weather forecast data from Open-Meteo.com",
                   "forecast_model_issue_time": None, "note": "Forecast retrieval time is shown; an upstream model issue time was not supplied by this API response."},
        "interpretation": "Experimental rainfall-based flood-risk screening for the selected coordinate/weather grid; not a flood forecast, official warning, or flood probability.",
    }


class OpenMeteoWeatherService:
    def __init__(self, timeout_seconds: float = 10.0, cache_seconds: float = 180.0,
                 transport: Callable[[str, float], dict] | None = None):
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = cache_seconds
        self.transport = transport or _open_meteo_json
        self._cache: dict[tuple[float, float], tuple[float, dict]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def locations() -> list[dict]:
        return [dict(item) for item in INDIA_LOCATIONS]

    @staticmethod
    def location(city_id: str) -> dict:
        try:
            return dict(_LOCATIONS_BY_ID[city_id.casefold()])
        except (KeyError, AttributeError) as exc:
            raise ValueError("unknown weather location") from exc

    def get_forecast(self, latitude: float, longitude: float, location_name: str = "Manual coordinates",
                     force_refresh: bool = False) -> dict:
        latitude, longitude = validate_coordinates(latitude, longitude)
        key = (latitude, longitude)
        now = time.monotonic()
        if not force_refresh:
            with self._lock:
                cached = self._cache.get(key)
                if cached and now - cached[0] < self.cache_seconds:
                    result = copy.deepcopy(cached[1])
                    result["cache_hit"] = True
                    result["cache_age_seconds"] = round(now - cached[0], 1)
                    result["location"]["name"] = location_name
                    return result
        params = urlencode({
            "latitude": latitude, "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "hourly": "precipitation,precipitation_probability,temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
            "timezone": WEATHER_TIMEZONE, "forecast_days": 2,
        })
        url = f"{OPEN_METEO_URL}?{params}"
        try:
            raw = self.transport(url, self.timeout_seconds)
        except WeatherServiceError:
            raise
        except Exception as exc:
            raise WeatherServiceError(f"Could not retrieve Open-Meteo forecast: {exc}") from exc
        retrieved = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result = build_weather_result(raw, latitude, longitude, location_name, retrieved)
        result["cache_hit"] = False
        result["cache_age_seconds"] = 0
        with self._lock:
            self._cache[key] = (time.monotonic(), copy.deepcopy(result))
        return result
