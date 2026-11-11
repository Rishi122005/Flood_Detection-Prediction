"""Dependency-light HTTP API and static frontend for local flood data."""

from __future__ import annotations

import argparse
import json
import logging
import math
import mimetypes
import hashlib
import re
import sys
import threading
import time as perf_timer
import tempfile
from datetime import date, datetime, time, timezone
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.glofas import GlofasError, _forecast_records, nearest_valid_cell, query_discharge_dataset
from forecasting.cwc_level_pilot import HFL_METRES
from forecasting.desinventar import HistoricalEventIndex
from .india_locations import INDIA_LOCATIONS
from .weather_service import OpenMeteoWeatherService, WeatherServiceError

LOGGER = logging.getLogger("flood_app")
APP_VERSION = "india-location-demo-6"
SCENE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
MODEL_SHA256 = "6f20437ef60a01d03c8f2b3ba93bbd04188278ae7906ca99b99618be48922720"
FUTURE_MODEL_UNAVAILABLE = {
    "status": "unavailable", "model_status": "not_trained",
    "target": "future flood-event occurrence", "probability": None,
    "reason": ("No independently evaluated future flood-event model is available. Official sources publish Alipingal/Devi warning 10.85 m, danger "
               "11.76 m, and historical HFL 13.11 m, but the local telemetry has unresolved readings above that HFL, a station-coordinate mismatch, "
               "substantial gaps, and no timezone declaration. The small clean chronological pilot is continuous gauge-level regression only and loses "
               "to persistence; it is not a flood prediction. Local GloFAS files are not time-aligned to this gauge."),
    "required_data": ["CWC confirmation of Alipingal station identity, coordinate, vertical datum, timezone, quality flags/corrections for extreme telemetry values",
                      "longer quality-controlled gauge series with genuine threshold events and complete observed non-event windows for a threshold model",
                      "recent independent chronological evaluation periods; issue-time-aligned rainfall/discharge features if used",
                      "verified spatial flood-event outcomes and monitoring coverage for any urban inundation target"],
}


def _finite_float(value: str | None, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _parse_filter_time(value: str | None, name: str) -> datetime | None:
    if value is None:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        parsed_date = date.fromisoformat(value)
        end_of_day = name == "until"
        return datetime.combine(parsed_date, time.max if end_of_day else time.min, tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{name} must be an ISO date or timezone-aware timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _wgs84_bounds(src) -> tuple[float, float, float, float] | None:
    if src.crs is None:
        return None
    if src.crs.to_epsg() == 4326:
        return (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
    try:
        from rasterio.warp import transform_bounds
        return transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
    except Exception:
        return None


def build_detection_catalog(prediction_dir: Path) -> list[dict]:
    """Read only existing prediction summaries and georeferenced rasters."""
    catalog = []
    if not prediction_dir.is_dir():
        return catalog
    for summary_path in sorted(prediction_dir.glob("*_summary.json")):
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            scene_id = summary_path.name[:-len("_summary.json")]
            if not SCENE_ID.fullmatch(scene_id):
                continue
            probability_path = prediction_dir / f"{scene_id}_probability.tif"
            mask_path = prediction_dir / f"{scene_id}_mask.tif"
            figure_path = prediction_dir / f"{scene_id}_prediction.png"
            if not probability_path.is_file() or not mask_path.is_file():
                continue
            with rasterio.open(probability_path) as src:
                bounds = _wgs84_bounds(src)
                if bounds is None or src.width < 1 or src.height < 1:
                    continue
                center_x, center_y = src.transform * (src.width / 2, src.height / 2)
                if src.crs.to_epsg() != 4326:
                    from rasterio.warp import transform
                    xvalues, yvalues = transform(src.crs, "EPSG:4326", [center_x], [center_y])
                    center_x, center_y = xvalues[0], yvalues[0]
                if (not all(math.isfinite(float(v)) for v in (*bounds, center_x, center_y))
                        or not -180 <= float(bounds[0]) <= 180
                        or not -180 <= float(bounds[2]) <= 180
                        or not -90 <= float(bounds[1]) <= 90
                        or not -90 <= float(bounds[3]) <= 90
                        or float(bounds[0]) > float(bounds[2])
                        or float(bounds[1]) > float(bounds[3])
                        or not -180 <= float(center_x) <= 180
                        or not -90 <= float(center_y) <= 90):
                    raise ValueError("prediction raster has invalid WGS84 center or bounds")
            catalog.append({
                "scene_id": scene_id, "center": {"latitude": center_y, "longitude": center_x},
                "bounds": {"west": bounds[0], "south": bounds[1], "east": bounds[2], "north": bounds[3]},
                "crs": "EPSG:4326", "width": summary.get("width"), "height": summary.get("height"),
                "acquisition_time": None,
                "date_status": "acquisition time not present in the prediction provenance",
                "valid_pixels": summary.get("valid_pixels"),
                "predicted_flood_pixels": summary.get("predicted_flood_pixels"),
                "predicted_flood_percent_valid": summary.get("predicted_flood_percent_valid"),
                "predicted_flood_area_km2": summary.get("predicted_flood_area_km2"),
                "area_method": summary.get("area_method"), "threshold": summary.get("threshold"),
                "model_version": f"best_unet_flood.keras sha256:{MODEL_SHA256[:12]}",
                "source_image_name": Path(summary.get("input", "")).name or None,
                "probability_file": probability_path.name, "mask_file": mask_path.name,
                "figure_url": f"/artifacts/{scene_id}.png" if figure_path.is_file() else None,
            })
        except (OSError, ValueError, rasterio.errors.RasterioError, KeyError) as exc:
            LOGGER.warning("Skip invalid detection summary %s: %s", summary_path, exc)
    return catalog


def query_detection_at_point(prediction_dir: Path, catalog: list[dict], latitude: float,
                             longitude: float) -> dict:
    hits = []
    for scene in catalog:
        b = scene["bounds"]
        if b["west"] <= longitude <= b["east"] and b["south"] <= latitude <= b["north"]:
            probability_path = prediction_dir / scene["probability_file"]
            mask_path = prediction_dir / scene["mask_file"]
            try:
                with rasterio.open(probability_path) as probability, rasterio.open(mask_path) as mask:
                    row, col = probability.index(longitude, latitude)
                    if not (0 <= row < probability.height and 0 <= col < probability.width):
                        continue
                    p = probability.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
                    m = mask.read(1, window=Window(col, row, 1, 1), masked=True)[0, 0]
                    if bool(getattr(p, "mask", False)) or bool(getattr(m, "mask", False)):
                        continue
                    hits.append({"status": "available", "scene_id": scene["scene_id"],
                                 "acquisition_time": scene["acquisition_time"],
                                 "predicted_flood": bool(float(m) == 1),
                                 "flood_probability_score": float(p),
                                 "score_warning": "Raw uncalibrated U-Net score; not an event probability.",
                                 "threshold": scene["threshold"], "model_version": scene["model_version"],
                                 "source_image_name": scene["source_image_name"],
                                 "scene_summary": scene})
            except (OSError, rasterio.errors.RasterioError, ValueError) as exc:
                LOGGER.warning("Could not query scene %s: %s", scene["scene_id"], exc)
    if hits:
        return {"status": "available", "results": hits}
    return {"status": "unavailable", "results": [],
            "reason": "No saved georeferenced prediction covers this coordinate."}


class FloodService:
    def __init__(self, prediction_dir: Path, forecast_path: Path | None, frontend_dir: Path,
                 event_path: Path | None = None):
        self.prediction_dir = prediction_dir.resolve()
        self.frontend_dir = frontend_dir.resolve()
        self.weather_service = OpenMeteoWeatherService()
        self.catalog = build_detection_catalog(self.prediction_dir)
        summary_sources = list(self.prediction_dir.glob("*_summary.json")) if self.prediction_dir.is_dir() else []
        self.detection_inventory = {
            "source_record_count": len(summary_sources),
            "valid_record_count": len(self.catalog),
            "invalid_record_count": max(0, len(summary_sources) - len(self.catalog)),
        }
        self.forecast_path = forecast_path.resolve() if forecast_path and forecast_path.is_file() else None
        self.forecast_dataset = None
        self.forecast_records = []
        self.forecast_lock = threading.Lock()
        self.india_location_cache = None
        self.cwc_demo_path = ROOT / "data/observations/cwc_mahanadi_telemetry_2021_2025.csv"
        self.cwc_demo_cache_path = ROOT / "outputs/forecasting/alipingal_demo_cache.json"
        self.cwc_demo_record = None
        self.cwc_demo_cache_error = None
        self.cwc_demo_lock = threading.Lock()
        self.event_index = HistoricalEventIndex(
            event_path or ROOT / "outputs/flood_events/desinventar_cleaned.csv")
        if self.forecast_path:
            try:
                self.forecast_dataset = rasterio.open(self.forecast_path)
                self.forecast_records = _forecast_records(self.forecast_dataset)
            except (OSError, rasterio.errors.RasterioError, ValueError) as exc:
                LOGGER.exception("Could not open GloFAS file %s", self.forecast_path)
                self.forecast_dataset = None
                self.forecast_path = None
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.model = None
        self.model_load_seconds = 0.0
        self.model_lock = threading.Lock()

    def process_satellite_upload(self, filename: str, content: bytes) -> dict:
        """Run the repository's VV/VH U-Net on one uploaded GeoTIFF."""
        request_started = perf_timer.perf_counter()
        validation_started = perf_timer.perf_counter()
        if not content or len(content) > 100 * 1024 * 1024:
            raise ValueError("Upload must be nonempty and no larger than 100 MiB")
        safe_name = Path(filename).name
        if Path(safe_name).suffix.casefold() not in {".tif", ".tiff"}:
            raise ValueError("This U-Net requires a two-band Sentinel-1 VV/VH GeoTIFF; PNG/JPEG and other formats are not compatible")
        validation_seconds = perf_timer.perf_counter() - validation_started
        import_started = perf_timer.perf_counter()
        from scripts.predict_flood import load_tflite_model, run
        runtime_import_seconds = perf_timer.perf_counter() - import_started
        checkpoint = ROOT / "models/best_unet_flood.keras"
        digest = hashlib.sha256(content).hexdigest()[:12]
        stem = "upload_" + digest
        run_id = f"upload_inference_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}_{digest}"
        output_dir = ROOT / "outputs" / run_id
        tflite_path = ROOT / "outputs/model_cache" / f"best_unet_flood_{MODEL_SHA256[:12]}.tflite"
        with tempfile.TemporaryDirectory(prefix="flood-upload-") as temp:
            temp_path = Path(temp)
            source = temp_path / f"{stem}.tif"
            file_started = perf_timer.perf_counter()
            source.write_bytes(content)
            try:
                with rasterio.open(source) as raster:
                    if raster.count < 2 or raster.width * raster.height > 4_000_000:
                        raise ValueError("GeoTIFF must contain two bands and no more than 4 million pixels (larger rasters need pre-tiling)")
                    if raster.crs is None:
                        raise ValueError("Uploaded GeoTIFF must include a CRS to preserve spatial metadata")
                    descriptions = [x.upper() if x else "" for x in raster.descriptions[:2]]
                    if any(descriptions) and not (descriptions[0].startswith("VV") and descriptions[1].startswith("VH")):
                        raise ValueError(f"Expected VV then VH bands; found {descriptions}")
                file_validation_seconds = perf_timer.perf_counter() - file_started
            except rasterio.errors.RasterioError as exc:
                raise ValueError("Could not read uploaded GeoTIFF") from exc
            with self.model_lock:
                if self.model is None:
                    self.model, self.model_load_seconds = load_tflite_model(checkpoint, tflite_path, threads=8)
                result = run(source, checkpoint, output_dir, .5, 512, 64, model=self.model,
                             model_load_seconds=self.model_load_seconds)
            result = dict(result)
            result["input"] = safe_name
            result["run_id"] = run_id
            prefix = f"/upload-artifacts/{run_id}/{stem}"
            result.update({"scene_id": stem, "kind": "flood-label segmentation", "input_name": safe_name,
                           "probability_url": f"{prefix}_probability.tif",
                           "mask_url": f"{prefix}_mask.tif",
                           "overlay_url": f"{prefix}_prediction.png"})
            result["timings"]["upload_validation_seconds"] = validation_seconds
            result["timings"]["tensorflow_import_seconds"] = runtime_import_seconds
            result["timings"]["upload_file_check_seconds"] = file_validation_seconds
            result["timings"]["upload_to_result_seconds"] = perf_timer.perf_counter() - request_started
            (output_dir / f"{stem}_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result

    def close(self):
        if self.forecast_dataset is not None:
            self.forecast_dataset.close()

    def availability(self) -> dict:
        bounds = [scene["bounds"] for scene in self.catalog]
        overall = None
        if bounds:
            overall = {"west": min(b["west"] for b in bounds), "south": min(b["south"] for b in bounds),
                       "east": max(b["east"] for b in bounds), "north": max(b["north"] for b in bounds)}
        hydro = {"status": "unavailable", "local_file_status": "missing", "source": None,
                 "kind": "external river discharge; not flood occurrence probability"}
        if self.forecast_dataset and self.forecast_records:
            latest_reference = max(item[1] for item in self.forecast_records)
            latest_cycle = [item for item in self.forecast_records if item[1] == latest_reference]
            latest_valid = max((item[2] for item in latest_cycle), default=None)
            stale = latest_valid is None or latest_valid < datetime.now(timezone.utc)
            hydro = {"status": "stale" if stale else "available", "local_file_status": "loaded",
                     "source": str(self.forecast_path), "forecast_issued_at": latest_reference.isoformat(),
                     "valid_until": latest_valid.isoformat() if latest_valid else None,
                     "available_horizons_hours": sorted({int((x[2]-x[1]).total_seconds()/3600) for x in latest_cycle}),
                     "kind": "external river discharge; not flood occurrence probability"}
        return {"status": "ok", "application_scope": "global queries; results only where local sources have coverage",
                "satellite_detection": {"status": "available" if self.catalog else "unavailable",
                                        "scene_count": len(self.catalog), "geographic_bounds": overall,
                                        "acquisition_dates_known": sum(x["acquisition_time"] is not None for x in self.catalog),
                                        "source": "local georeferenced U-Net probability/mask GeoTIFFs"},
                "hydrological_forecast": hydro,
                "historical_event_reports": {
                    "status": "available" if self.event_index.count else "unavailable",
                    "record_count": self.event_index.count,
                    "source": "DesInventar_Geocoded.csv; historical reports only",
                    "interpretation": "Not exposure-normalized risk and not a future-event probability.",
                },
                "model_generated_flood_event_probability": dict(FUTURE_MODEL_UNAVAILABLE),
                "place_name_search": {"status": "limited", "method": "local scene ID search only; no global gazetteer installed"},
                "started_at": self.started_at}

    def india_locations(self) -> dict:
        """List curated Indian city presets with actual local river-grid coverage."""
        if self.india_location_cache is not None:
            return self.india_location_cache
        if not self.forecast_dataset or not self.forecast_records:
            return {"status": "unavailable", "locations": [],
                    "reason": "No compatible local river-discharge forecast file is configured."}
        latest_reference = max(item[1] for item in self.forecast_records)
        latest_cycle = [item for item in self.forecast_records if item[1] == latest_reference]
        reference_band = latest_cycle[0][0]
        latest_valid = max(item[2] for item in latest_cycle)
        freshness = "stale" if latest_valid < datetime.now(timezone.utc) else "available"
        locations = []
        with self.forecast_lock:
            for place in INDIA_LOCATIONS:
                cell = nearest_valid_cell(self.forecast_dataset, place["latitude"],
                                          place["longitude"], reference_band, 30.0)
                supported = cell is not None and not cell["too_far"]
                locations.append({**place,
                                  "coverage_status": "supported" if supported else "no_nearby_river_cell",
                                  "nearest_river_cell_distance_km": round(cell["distance_km"], 3) if cell else None,
                                  "data_status": freshness,
                                  "latest_valid_until": latest_valid.isoformat()})
        self.india_location_cache = {
            "status": "ok", "source": "local ECMWF river-discharge GRIB; release identity unverified",
            "coverage_definition": "A valid river-network grid cell is within 30 km; this does not prove local hydrological representativeness.",
            "forecast_issued_at": latest_reference.isoformat(),
            "valid_until": latest_valid.isoformat(), "locations": locations,
        }
        return self.india_location_cache

    def query(self, latitude: float, longitude: float, horizon_hours: int | None = None,
              event_radius_km: float = 25.0) -> dict:
        if not math.isfinite(latitude) or not -90 <= latitude <= 90:
            raise ValueError("latitude must be between -90 and 90")
        if not math.isfinite(longitude) or not -180 <= longitude <= 180:
            raise ValueError("longitude must be between -180 and 180")
        if horizon_hours is not None and horizon_hours not in {24, 48, 72}:
            raise ValueError("horizon_hours must be one of 24, 48, or 72")
        detection = query_detection_at_point(self.prediction_dir, self.catalog, latitude, longitude)
        historical_events = self.event_index.nearby(latitude, longitude, event_radius_km)
        if self.forecast_dataset:
            with self.forecast_lock:
                discharge = query_discharge_dataset(self.forecast_dataset, latitude, longitude,
                                                    records=self.forecast_records)
            if horizon_hours is not None and discharge.get("forecasts"):
                discharge["forecasts"] = [x for x in discharge["forecasts"]
                                           if x["forecast_horizon_hours"] == horizon_hours]
                if discharge["forecasts"]:
                    selected = discharge["forecasts"][0]
                    discharge["forecast_issued_at"] = selected["forecast_issued_at"]
                    discharge["valid_from"] = selected["valid_from"]
                    discharge["valid_until"] = selected["valid_until"]
                else:
                    discharge["status"] = "unsupported_horizon"
                    discharge["reason"] = "The local file has no record for this requested horizon."
            discharge["requested_horizon_hours"] = horizon_hours
            if discharge.get("status") == "available":
                discharge["current_forecasts"] = list(discharge.get("forecasts", []))
                discharge["archived_forecasts"] = []
                discharge["availability_message"] = None
            else:
                discharge["current_forecasts"] = []
                discharge["archived_forecasts"] = [
                    {**record, "record_status": "archived_forecast_not_current"}
                    for record in discharge.get("forecasts", [])
                ]
                discharge["availability_message"] = (
                    f"{horizon_hours or 24}-hour forecast unavailable — no valid future discharge data is available."
                )
            discharge["observation_status"] = "not_in_forecast_product"
            discharge["latest_observation"] = None
        else:
            discharge = {"status": "unavailable", "coverage_status": "source_file_missing",
                         "probability": None, "reason": "No local GloFAS forecast file is configured."}
            discharge["requested_horizon_hours"] = horizon_hours
            discharge["current_forecasts"] = []
            discharge["archived_forecasts"] = []
            discharge["availability_message"] = (
                f"{horizon_hours or 24}-hour forecast unavailable — no valid future discharge data is available."
            )
            discharge["observation_status"] = "unavailable"
            discharge["latest_observation"] = None
        future_event = dict(FUTURE_MODEL_UNAVAILABLE)
        future_event.update({"forecast_horizon_hours": None,
                             "requested_horizon_hours": horizon_hours})
        return {"status": "partial" if detection["status"] == "available" or discharge.get("forecasts") or historical_events.get("status") == "available" else "unavailable",
                "location": {"latitude": latitude, "longitude": longitude},
                "forecast_issued_at": discharge.get("forecast_issued_at") if discharge.get("status") == "available" else None,
                "valid_from": discharge.get("valid_from") if discharge.get("status") == "available" else None,
                "valid_until": discharge.get("valid_until") if discharge.get("status") == "available" else None,
                "requested_horizon_hours": horizon_hours,
                "forecast_horizon_hours": horizon_hours if discharge.get("status") == "available" else None,
                "risk_level": None, "probability": None,
                "coverage_status": {"satellite_detection": detection["status"],
                                    "glofas": discharge.get("coverage_status", discharge["status"])},
                "satellite_detection": detection,
                "historical_event_reports": historical_events,
                "hydrological_forecast": discharge,
                "future_flood_event_prediction": future_event,
                "limitations": ["Satellite segmentation describes the supplied acquisition, not a future flood.",
                                "GloFAS discharge is an external hydrological forecast and is not a flood probability."]}

    def experimental_gauge_demo(self, station_id: str) -> dict:
        """Classify the latest screened historical Alipingal reading; never call it a forecast."""
        if station_id != "alipingal-devi":
            return {"status": "unsupported_location", "station_id": station_id,
                    "risk_category": None, "probability": None,
                    "reason": "Only the Alipingal/Devi CWC telemetry station has a verified published threshold in this demo."}
        if not self.cwc_demo_path.is_file():
            return {"status": "unavailable", "station_id": station_id,
                    "risk_category": None, "probability": None,
                    "reason": f"CWC telemetry CSV is missing: {self.cwc_demo_path.name}"}
        with self.cwc_demo_lock:
            if self.cwc_demo_record is None and self.cwc_demo_cache_error is None:
                try:
                    stat = self.cwc_demo_path.stat()
                    if not self.cwc_demo_cache_path.is_file():
                        raise ValueError("compact CWC cache is missing")
                    cache = json.loads(self.cwc_demo_cache_path.read_text(encoding="utf-8"))
                    if (cache.get("schema_version") != 1 or cache.get("station_id") != station_id
                            or cache.get("source_size_bytes") != stat.st_size
                            or cache.get("source_mtime_ns") != stat.st_mtime_ns):
                        raise ValueError("compact CWC cache does not match the current source CSV")
                    self.cwc_demo_record = cache
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    self.cwc_demo_cache_error = str(exc)
                    LOGGER.warning("Alipingal demo cache unavailable: %s", exc)
            cache = self.cwc_demo_record
            cache_error = self.cwc_demo_cache_error
        if not cache:
            return {"status": "unavailable", "station_id": station_id,
                    "risk_category": None, "probability": None,
                    "reason": f"The compact Alipingal cache is unavailable ({cache_error}); run `python scripts/build_cwc_demo_cache.py` to refresh it."}
        latest = cache.get("latest_observation") or {}
        observed_at = latest.get("observed_at")
        level = latest.get("level_m")
        if not isinstance(observed_at, str) or not isinstance(level, (int, float)):
            return {"status": "unavailable", "station_id": station_id,
                    "risk_category": None, "probability": None,
                    "reason": "The compact Alipingal cache has no valid screened latest observation."}
        previous_record = cache.get("observation_24h_prior")
        previous = previous_record.get("level_m") if previous_record else None
        change = float(level) - float(previous) if previous is not None else None
        # Source timestamps have no declared timezone. Compare calendar dates only,
        # and suppress threshold classification once the observation is stale.
        try:
            observed_date = date.fromisoformat(observed_at[:10])
            age_days = max(0, (datetime.now(timezone.utc).date() - observed_date).days)
        except ValueError:
            return {"status": "unavailable", "station_id": station_id,
                    "risk_category": None, "probability": None,
                    "reason": "The screened observation timestamp is invalid; threshold classification is unavailable."}
        freshness = "fresh" if age_days <= 2 else "stale"
        if freshness == "stale":
            category = None
            rule = None
            status_message = "Historical observation only; current threshold classification is unavailable because the data are stale."
        elif level >= 11.76:
            category = "Danger level exceeded"
            rule = "Recorded gauge level is at or above the published danger level (11.76 m)."
            status_message = category
        elif level >= 10.85:
            category = "Warning level exceeded"
            rule = "Recorded gauge level is at or above warning (10.85 m) and below danger (11.76 m)."
            status_message = category
        else:
            category = "Below warning"
            rule = "Recorded gauge level is below the published warning level (10.85 m)."
            status_message = category
        return {
            "status": "historical_demo_estimate", "model_type": "Experimental Demo Estimate · threshold heuristic",
            "station_id": station_id, "station_name": cache.get("station_name", "Alipingal / Alipingala, Devi River, Odisha"),
            "risk_category": category, "probability": None,
            "freshness": freshness, "age_days_approx": age_days,
            "classification_status": "unavailable_stale" if freshness == "stale" else "classified",
            "status_message": status_message,
            "requested_horizon_hours": 24, "forecast_horizon_hours": None,
            "interpretation": "Threshold category is shown only for a fresh observation; stale readings remain historical evidence. This is not a future flood forecast.",
            "inputs": {"gauge_level_m": float(level), "observed_at": observed_at,
                       "timestamp_timezone": "not specified by source; recorded wall-clock time",
                       "warning_level_m": 10.85, "danger_level_m": 11.76,
                       "historical_hfl_m": HFL_METRES,
                       "level_24h_earlier_m": float(previous) if previous is not None else None,
                       "change_24h_m": change},
            "rule": rule,
            "limitations": [f"Latest screened observation is from {observed_at[:10]}; freshness is approximate because the source timezone is unspecified. No next-24-hour forecast is generated.",
                            "A threshold category is emitted only for a fresh reading. This is not a trained model or calibrated probability.",
                            "CWC has not reconciled local station coordinates/datum or explained source readings above the published HFL; this demo excludes readings outside 0–13.11 m.",
                            "A river-gauge category does not establish urban flooding."],
            "source": "CWC Mahanadi telemetry CSV and official Alipingal/Devi published warning/danger/HFL levels",
        }

    def river_level_prediction_demo(self, station_id: str) -> dict:
        """Expose the honest 24h model state and chronological diagnostic metrics."""
        observed = self.experimental_gauge_demo(station_id)
        if observed["status"] != "historical_demo_estimate":
            return {"status": observed["status"], "station_id": station_id,
                    "latest_observation": None, "predicted_level_24h_m": None,
                    "model_evaluation": None, "reason": observed.get("reason")}
        pilot_path = ROOT / "reports/level_forecast_pilot.json"
        try:
            pilot = json.loads(pilot_path.read_text(encoding="utf-8"))
            ridge, baseline = pilot["ridge"], pilot["persistence"]
        except (OSError, ValueError, KeyError) as exc:
            LOGGER.warning("Could not load river-level pilot metrics: %s", exc)
            ridge = baseline = None
            pilot = {}
        timestamp = observed["inputs"]["observed_at"]
        try:
            observation_date = datetime.fromisoformat(timestamp).date()
            age_days = max(0, (datetime.now(timezone.utc).date() - observation_date).days)
        except ValueError:
            age_days = None
        return {
            "status": "forecast_unavailable",
            "station_id": station_id,
            "station_name": observed["station_name"],
            "requested_horizon_hours": 24,
            "forecast_horizon_hours": None,
            "latest_observation": {**observed["inputs"], "age_days_approx": age_days,
                                   "freshness": "stale" if age_days is None or age_days > 2 else "recent"},
            "predicted_level_24h_m": None,
            "model_evaluation": {
                "name": "Ridge regression candidate (rejected; diagnostic only)",
                "test_year": pilot.get("test_year"),
                "test_samples": pilot.get("split", {}).get("2023"),
                "test_target_range_m": pilot.get("test_target_range_m"),
                "ridge_mae_m": ridge.get("mae_m") if ridge else None,
                "ridge_rmse_m": ridge.get("rmse_m") if ridge else None,
                "persistence_mae_m": baseline.get("mae_m") if baseline else None,
                "persistence_rmse_m": baseline.get("rmse_m") if baseline else None,
                "model_artifact_saved": False,
                "evaluation_source": "reports/level_forecast_pilot.json",
            },
            "reason": "No useful 24-hour forecast is available: the latest screened observation is stale, and the small 2023 Ridge test was worse than persistence on a near-constant low-stage sample.",
            "limitations": ["The 2023 test has only 28 windows with target levels 4.001–4.002 m; this does not establish performance at high water.",
                            "The continuous-level pilot predicts gauge level, not flood occurrence or urban inundation.",
                            "Telemetry timestamp timezone, station coordinate/datum, and readings above historical HFL require CWC clarification.",
                            "No forecast value is generated from stale observations."],
            "source": "CWC Mahanadi telemetry; chronological pilot metrics",
        }


def make_handler(service: FloodService):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FloodMonitoring/1.0"

        def _json(self, payload: dict, status: int = 200):
            encode_started = perf_timer.perf_counter()
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
            if isinstance(payload.get("timings"), dict):
                payload["timings"]["response_serialization_seconds"] = perf_timer.perf_counter() - encode_started
                body = json.dumps(payload, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Flood-App-Version", APP_VERSION)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            if parsed.path in {"/", "/index.html"}:
                return self._static(service.frontend_dir / "index.html")
            if parsed.path.startswith("/assets/"):
                rel = unquote(parsed.path[len("/assets/"):])
                if "/" in rel or ".." in rel:
                    return self._json({"error": "invalid asset path"}, 400)
                return self._static(service.frontend_dir / "assets" / rel)
            if parsed.path.startswith("/artifacts/"):
                scene_id = unquote(parsed.path[len("/artifacts/"):])
                if not SCENE_ID.fullmatch(scene_id) or not scene_id.endswith(".png"):
                    return self._json({"error": "invalid artifact name"}, 400)
                scene_id = scene_id[:-4]
                if not any(x["scene_id"] == scene_id and x["figure_url"] for x in service.catalog):
                    return self._json({"error": "artifact not found"}, 404)
                return self._static(service.prediction_dir / f"{scene_id}_prediction.png")
            if parsed.path.startswith("/upload-artifacts/"):
                name = unquote(parsed.path[len("/upload-artifacts/"):])
                match = re.fullmatch(
                    r"(upload_inference_\d{8}_\d{6}_\d{6}_[a-f0-9]{12})/(upload_[a-f0-9]{12}_(?:probability\.tif|mask\.tif|prediction\.png))",
                    name)
                if not match:
                    return self._json({"error": "invalid artifact name"}, 400)
                run_dir = (ROOT / "outputs" / match.group(1)).resolve()
                if run_dir.parent != (ROOT / "outputs").resolve():
                    return self._json({"error": "invalid artifact path"}, 400)
                return self._static(run_dir / match.group(2))
            if parsed.path.startswith("/before-after-artifacts/"):
                name = unquote(parsed.path[len("/before-after-artifacts/"):])
                allowed = {
                    "before_after_comparison.png",
                    "before_2016-07-19_VV_VH.tif", "after_2016-08-12_VV_VH.tif",
                    "before_2016-07-19_VV_VH_prediction.png",
                    "after_2016-08-12_VV_VH_prediction.png",
                    "before_2016-07-19_VV_VH_mask.tif", "after_2016-08-12_VV_VH_mask.tif",
                    "before_2016-07-19_VV_VH_probability.tif", "after_2016-08-12_VV_VH_probability.tif",
                    "change_mask.tif",
                }
                if name not in allowed:
                    return self._json({"error": "invalid before/after artifact name"}, 400)
                root = ROOT / "outputs/before_after_India_1017769"
                if name.startswith("before_") and name.endswith(("_prediction.png", "_mask.tif", "_probability.tif")):
                    path = root / "predictions/before" / name
                elif name.startswith("after_") and name.endswith(("_prediction.png", "_mask.tif", "_probability.tif")):
                    path = root / "predictions/after" / name
                else:
                    path = root / name
                return self._static(path)
            if parsed.path == "/api/before-after/demo":
                report_path = ROOT / "outputs/before_after_India_1017769/comparison_summary.json"
                try:
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                    pair_metadata = json.loads((report_path.parent / "pair_metadata.json").read_text(encoding="utf-8"))
                    report["scene_ids"] = {key: value["item_id"] for key, value in pair_metadata["pair"].items()}
                    report["acquisitions"] = {key: {"acquisition_time": value["acquisition_time"],
                                                     "relative_orbit": value["relative_orbit"],
                                                     "orbit_state": value["orbit_state"],
                                                     "polarizations": value["polarizations"]}
                                               for key, value in pair_metadata["pair"].items()}
                    report["status"] = "exploratory_pair_available"
                    report["artifact_urls"] = {key: f"/before-after-artifacts/{Path(value).name}"
                                               for key, value in report["artifacts"].items()}
                    report["artifact_urls"].update({"comparison_figure": "/before-after-artifacts/before_after_comparison.png",
                        "change_raster": "/before-after-artifacts/change_mask.tif"})
                    return self._json(report)
                except (OSError, ValueError) as exc:
                    return self._json({"status": "unavailable", "reason": f"Pair outputs are unavailable: {exc}"}, 503)
            if parsed.path == "/api/health":
                return self._json({"status": "ok", "application": "Flood Monitoring",
                                   "api_version": APP_VERSION})
            if parsed.path == "/api/availability":
                return self._json(service.availability())
            if parsed.path == "/api/india-locations":
                return self._json(service.india_locations())
            if parsed.path == "/api/weather-risk/locations":
                return self._json({"status": "ok", "locations": service.weather_service.locations()})
            if parsed.path == "/api/weather-risk":
                try:
                    city_id = params.get("city", [""])[0]
                    if city_id:
                        location = service.weather_service.location(city_id)
                        latitude, longitude, location_name = location["latitude"], location["longitude"], location["name"]
                    else:
                        if "lat" not in params or "lon" not in params:
                            raise ValueError("city or both lat and lon query parameters are required")
                        latitude = _finite_float(params["lat"][0], "latitude")
                        longitude = _finite_float(params["lon"][0], "longitude")
                        location_name = "Manual coordinates"
                    result = service.weather_service.get_forecast(
                        latitude, longitude, location_name,
                        force_refresh=params.get("refresh", ["0"])[0] == "1")
                    return self._json(result)
                except ValueError as exc:
                    return self._json({"status": "invalid_request", "error": str(exc)}, 400)
                except WeatherServiceError as exc:
                    return self._json({"status": "unavailable", "error": str(exc)}, exc.status)
                except Exception as exc:
                    LOGGER.exception("Open-Meteo weather request failed")
                    return self._json({"status": "unavailable", "error": "Weather forecast request failed"}, 502)
            if parsed.path == "/api/demo-prediction":
                station_id = params.get("station", [""])[0]
                if not station_id:
                    return self._json({"status": "invalid_request", "risk_category": None,
                                        "probability": None, "error": "station query parameter is required"}, 400)
                result = service.experimental_gauge_demo(station_id)
                status = 404 if result["status"] == "unsupported_location" else 200
                return self._json(result, status)
            if parsed.path == "/api/river-level-prediction":
                station_id = params.get("station", [""])[0]
                if not station_id:
                    return self._json({"status": "invalid_request", "predicted_level_24h_m": None,
                                        "error": "station query parameter is required"}, 400)
                result = service.river_level_prediction_demo(station_id)
                status = 404 if result["status"] == "unsupported_location" else 200
                return self._json(result, status)
            if parsed.path == "/api/detections":
                scenes = service.catalog
                if "q" in params:
                    query = params["q"][0].casefold()
                    scenes = [s for s in scenes if query in s["scene_id"].casefold()]
                if "bbox" in params:
                    try:
                        west, south, east, north = [float(x) for x in params["bbox"][0].split(",")]
                        if not all(math.isfinite(x) for x in (west, south, east, north)) or not (-180 <= west <= 180 and -180 <= east <= 180 and -90 <= south < north <= 90):
                            raise ValueError("bbox outside coordinate bounds")
                        if west <= east:
                            scenes = [s for s in scenes if s["bounds"]["east"] >= west and s["bounds"]["west"] <= east and s["bounds"]["north"] >= south and s["bounds"]["south"] <= north]
                        else:
                            scenes = [s for s in scenes if (s["bounds"]["east"] >= west or s["bounds"]["west"] <= east) and s["bounds"]["north"] >= south and s["bounds"]["south"] <= north]
                    except ValueError as exc:
                        return self._json({"error": f"invalid bbox: {exc}"}, 400)
                try:
                    since = _parse_filter_time(params.get("since", [None])[0], "since")
                    until = _parse_filter_time(params.get("until", [None])[0], "until")
                    if since and until and since > until:
                        raise ValueError("since must not be after until")
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                time_filtered = since is not None or until is not None
                unknown_dates = sum(scene["acquisition_time"] is None for scene in scenes) if time_filtered else 0
                if time_filtered:
                    filtered = []
                    for scene in scenes:
                        stamp = _parse_filter_time(scene["acquisition_time"], "acquisition_time") if scene["acquisition_time"] else None
                        if stamp is None:
                            continue
                        if since and stamp < since or until and stamp > until:
                            continue
                        filtered.append(scene)
                    scenes = filtered
                return self._json({"count": len(scenes), "results": scenes,
                                   "source_record_count": service.detection_inventory["source_record_count"],
                                   "valid_record_count": service.detection_inventory["valid_record_count"],
                                   "invalid_record_count": service.detection_inventory["invalid_record_count"],
                                   "displayed_record_count": len(scenes),
                                   "time_filter": {"applied": time_filtered, "since": params.get("since", [None])[0],
                                                   "until": params.get("until", [None])[0],
                                                   "excluded_unknown_acquisition_time": unknown_dates}})
            if parsed.path == "/api/query":
                try:
                    if "lat" not in params or "lon" not in params:
                        raise ValueError("lat and lon query parameters are required")
                    lat = _finite_float(params["lat"][0], "lat")
                    lon = _finite_float(params["lon"][0], "lon")
                    horizon = int(params["horizon_hours"][0]) if "horizon_hours" in params else None
                    radius = _finite_float(params["event_radius_km"][0], "event_radius_km") if "event_radius_km" in params else 25.0
                    return self._json(service.query(lat, lon, horizon, radius))
                except ValueError as exc:
                    return self._json({"error": str(exc)}, 400)
                except GlofasError as exc:
                    return self._json({"error": str(exc)}, 422)
                except Exception as exc:
                    LOGGER.exception("Location query failed")
                    return self._json({"error": "location query failed", "detail": str(exc)}, 503)
            return self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/satellite/process":
                return self._json({"error": "not found"}, 404)
            try:
                request_started = perf_timer.perf_counter()
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 100 * 1024 * 1024:
                    return self._json({"error": "Upload must be nonempty and no larger than 100 MiB"}, 413)
                body = self.rfile.read(length)
                message = BytesParser(policy=default).parsebytes(
                    b"Content-Type: " + self.headers.get("Content-Type", "").encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + body)
                if not message.is_multipart():
                    return self._json({"error": "Use multipart/form-data with a file field named image"}, 400)
                part = next((p for p in message.iter_parts() if p.get_param("name", header="content-disposition") == "image"), None)
                if part is None or not part.get_filename():
                    return self._json({"error": "Missing image upload field"}, 400)
                multipart_parse_seconds = perf_timer.perf_counter() - request_started
                result = service.process_satellite_upload(part.get_filename(), part.get_payload(decode=True) or b"")
                result["timings"]["http_multipart_parse_seconds"] = multipart_parse_seconds
                return self._json(result)
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            except Exception as exc:
                LOGGER.exception("Satellite upload processing failed")
                return self._json({"error": "Satellite processing failed", "detail": str(exc)}, 422)

        def _static(self, path: Path):
            try:
                body = path.read_bytes()
            except OSError:
                return self._json({"error": "file not found"}, 404)
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if content_type == "text/html":
                content_type += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Flood-App-Version", APP_VERSION)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *args):
            LOGGER.info("%s - %s", self.address_string(), fmt % args)

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--predictions", type=Path, default=Path("outputs/india/predictions"))
    parser.add_argument("--glofas", type=Path, default=Path("data/glofas/data.grib"))
    parser.add_argument("--frontend", type=Path, default=ROOT / "frontend")
    parser.add_argument("--historical-events", type=Path,
                        default=ROOT / "outputs/flood_events/desinventar_cleaned.csv")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    forecast_path = args.glofas if args.glofas.is_file() else None
    service = FloodService(args.predictions, forecast_path, args.frontend, args.historical_events)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(service))
    LOGGER.info("Serving %d georeferenced detections on http://%s:%d", len(service.catalog), args.host, args.port)
    LOGGER.info("External GloFAS file: %s", service.forecast_path or "unavailable")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Stopping server")
    finally:
        server.server_close()
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
