import tempfile
import unittest
from email.message import Message
import csv
import numpy as np
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
import rasterio
from rasterio.transform import from_origin

from src.flood_app.server import FloodService, build_detection_catalog, make_handler
from src.flood_app.india_locations import INDIA_LOCATIONS
from forecasting.desinventar import HistoricalEventIndex, _date_parts


ROOT = Path(__file__).resolve().parents[1]


class GlobalServiceTests(unittest.TestCase):
    def test_deployment_can_use_verified_compact_cwc_cache_without_raw_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            service.cwc_demo_path = Path(temp) / "cwc-source-not-bundled.csv"
            service.cwc_demo_cache_path = ROOT / "outputs/forecasting/alipingal_demo_cache.json"
            try:
                with patch.dict("os.environ", {"FLOOD_ALLOW_PREBUILT_CWC_CACHE": "1"}):
                    result = service.experimental_gauge_demo("alipingal-devi")
                self.assertEqual(result["status"], "historical_demo_estimate")
                self.assertEqual(result["freshness"], "stale")
                self.assertIsNone(result["risk_category"])
            finally:
                service.close()

    def test_cors_preflight_allows_only_configured_frontend_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                handler = make_handler(service).__new__(make_handler(service))
                handler.headers = Message()
                handler.headers["Origin"] = "https://flood-demo.vercel.app"
                handler.send_response = Mock()
                handler.send_header = Mock()
                handler.end_headers = Mock()
                with patch.dict("os.environ", {"CORS_ALLOWED_ORIGINS": "https://flood-demo.vercel.app"}):
                    handler.do_OPTIONS()
                handler.send_response.assert_called_once_with(204)
                headers = {call.args[0]: call.args[1] for call in handler.send_header.call_args_list}
                self.assertEqual(headers["Access-Control-Allow-Origin"], "https://flood-demo.vercel.app")
                self.assertEqual(headers["Access-Control-Allow-Methods"], "GET, POST, OPTIONS")
            finally:
                service.close()

    def test_detection_catalog_rejects_out_of_range_wgs84_georeferencing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "outside_summary.json").write_text("{}", encoding="utf-8")
            profile = {"driver": "GTiff", "width": 2, "height": 2, "count": 1,
                       "dtype": "float32", "crs": "EPSG:4326", "transform": from_origin(0, 95, 1, 1)}
            for suffix in ("probability", "mask"):
                with rasterio.open(root / f"outside_{suffix}.tif", "w", **profile) as dst:
                    dst.write(np.zeros((2, 2), dtype="float32"), 1)
            self.assertEqual(build_detection_catalog(root), [])

    def test_detection_endpoint_reports_valid_invalid_and_displayed_counts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "broken_summary.json").write_text("{not json", encoding="utf-8")
            service = FloodService(root, None, ROOT / "frontend")
            try:
                handler_type = make_handler(service)
                handler = handler_type.__new__(handler_type)
                handler.path = "/api/detections"
                handler._json = Mock()
                handler.do_GET()
                payload = handler._json.call_args.args[0]
                self.assertEqual(payload["source_record_count"], 1)
                self.assertEqual(payload["valid_record_count"], 0)
                self.assertEqual(payload["invalid_record_count"], 1)
                self.assertEqual(payload["displayed_record_count"], 0)
            finally:
                service.close()

    def test_stale_external_discharge_is_archived_not_a_current_forecast(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            service.forecast_dataset = type("FakeForecastDataset", (), {"close": lambda self: None})()
            service.forecast_records = [(1, datetime(2025, 1, 20, tzinfo=timezone.utc),
                                         datetime(2025, 1, 21, tzinfo=timezone.utc), {})]
            stale_record = {"forecast_issued_at": "2025-01-20T00:00:00+00:00",
                            "valid_from": "2025-01-20T00:00:00+00:00",
                            "valid_until": "2025-01-21T00:00:00+00:00",
                            "forecast_horizon_hours": 24, "river_discharge_m3_s": 0.453125}
            try:
                with patch("src.flood_app.server.query_discharge_dataset", return_value={
                    "status": "stale", "coverage_status": "river_cell_found_upstream_area_unverified",
                    "forecasts": [stale_record], "source_cell": {"distance_km": 1.9},
                    "source": "test GRIB", "probability": None,
                }):
                    result = service.query(28.6, 77.2, horizon_hours=24)
                forecast = result["hydrological_forecast"]
                self.assertEqual(forecast["availability_message"],
                    "24-hour forecast unavailable \u2014 no valid future discharge data is available.")
                self.assertEqual(forecast["current_forecasts"], [])
                self.assertEqual(forecast["archived_forecasts"][0]["river_discharge_m3_s"], 0.453125)
                self.assertIsNone(result["forecast_issued_at"])
                self.assertIsNone(result["forecast_horizon_hours"])
                self.assertIsNone(forecast["latest_observation"])
                self.assertIsNone(result["probability"])
            finally:
                service.close()

    def test_before_after_demo_api_exposes_real_aligned_pair_and_artifact_allowlist(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                handler_type = make_handler(service)
                handler = handler_type.__new__(handler_type)
                handler.path = "/api/before-after/demo"
                handler._json = Mock()
                handler.do_GET()
                payload = handler._json.call_args.args[0]
                self.assertEqual(payload["status"], "exploratory_pair_available")
                self.assertTrue(payload["grid_aligned"])
                self.assertEqual(payload["before_date"][:10], "2016-07-19")
                self.assertEqual(payload["after_date"][:10], "2016-08-12")
                self.assertIn("comparison_figure", payload["artifact_urls"])
                self.assertEqual(payload["newly_segmented_pixels"], 0)
                handler.path = "/before-after-artifacts/../../models/best_unet_flood.keras"
                handler._json = Mock()
                handler.do_GET()
                self.assertEqual(handler._json.call_args.args[1], 400)
            finally:
                service.close()

    def test_india_location_catalog_uses_measured_river_grid_coverage_and_staleness(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                issued = datetime(2025, 1, 20, tzinfo=timezone.utc)
                service.forecast_dataset = type("FakeForecastDataset", (), {"close": lambda self: None})()
                service.forecast_records = [(1, issued, issued + timedelta(hours=72), {})]
                with patch("src.flood_app.server.nearest_valid_cell", return_value={
                    "too_far": False, "distance_km": 2.5,
                }) as nearest:
                    result = service.india_locations()
                self.assertEqual(len(result["locations"]), len(INDIA_LOCATIONS))
                self.assertTrue(all(x["coverage_status"] == "supported" for x in result["locations"]))
                self.assertTrue(all(x["data_status"] == "stale" for x in result["locations"]))
                self.assertEqual(nearest.call_count, len(INDIA_LOCATIONS))
                self.assertIn("does not prove local hydrological representativeness", result["coverage_definition"])
                self.assertIs(service.india_locations(), result)
            finally:
                service.close()

    def test_event_probability_stays_unavailable_without_model(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                result = service.query(0.0, 0.0)
                self.assertEqual(result["future_flood_event_prediction"]["status"], "unavailable")
                self.assertIsNone(result["future_flood_event_prediction"]["forecast_horizon_hours"])
                self.assertEqual(result["future_flood_event_prediction"]["requested_horizon_hours"], None)
                self.assertIsNone(result["probability"])
                self.assertEqual(result["hydrological_forecast"]["status"], "unavailable")
                self.assertIn("GloFAS files are not time-aligned", result["future_flood_event_prediction"]["reason"])
                self.assertIn("Official sources publish Alipingal/Devi", result["future_flood_event_prediction"]["reason"])
                self.assertIn("danger 11.76 m", result["future_flood_event_prediction"]["reason"])
                self.assertIn("coordinate mismatch", result["future_flood_event_prediction"]["reason"])
                self.assertTrue(result["future_flood_event_prediction"]["required_data"])
            finally:
                service.close()

    def test_experimental_gauge_demo_formats_timestamped_threshold_rule_without_probability(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            csv_path = root / "cwc.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=["Station", "Data Acquisition Time",
                    "River Water Level Telemetry Hourly (meter)"])
                writer.writeheader()
                writer.writerow({"Station": "Alipingal", "Data Acquisition Time": "01-06-2024 00:00",
                                 "River Water Level Telemetry Hourly (meter)": "10.7"})
                writer.writerow({"Station": "Alipingal", "Data Acquisition Time": "02-06-2024 00:00",
                                 "River Water Level Telemetry Hourly (meter)": "11.0"})
            service = FloodService(root / "predictions", None, ROOT / "frontend")
            service.cwc_demo_path = csv_path
            service.cwc_demo_record = {
                "station_name": "Alipingal / Devi test gauge",
                "latest_observation": {"observed_at": "2024-06-02T00:00:00", "level_m": 11.0},
                "observation_24h_prior": {"observed_at": "2024-06-01T00:00:00", "level_m": 10.7},
            }
            try:
                result = service.experimental_gauge_demo("alipingal-devi")
                self.assertEqual(result["status"], "historical_demo_estimate")
                self.assertIsNone(result["risk_category"])
                self.assertEqual(result["freshness"], "stale")
                self.assertEqual(result["classification_status"], "unavailable_stale")
                self.assertIsNone(result["rule"])
                self.assertIsNone(result["probability"])
                self.assertIsNone(result["forecast_horizon_hours"])
                self.assertEqual(result["inputs"]["observed_at"], "2024-06-02T00:00:00")
                self.assertAlmostEqual(result["inputs"]["change_24h_m"], 0.3)
                self.assertIn("not a future flood forecast", result["interpretation"])
                self.assertEqual(result["inputs"]["historical_hfl_m"], 13.11)
                self.assertIn("stale", result["status_message"])
                self.assertIn("not specified", result["inputs"]["timestamp_timezone"])
                handler_type = make_handler(service)
                handler = handler_type.__new__(handler_type)
                handler.path = "/api/demo-prediction?station=alipingal-devi"
                handler._json = Mock()
                handler.do_GET()
                handler._json.assert_called_once()
                self.assertIsNone(handler._json.call_args.args[0]["risk_category"])
                self.assertEqual(handler._json.call_args.args[1], 200)
                handler.path = "/api/demo-prediction?station=chennai"
                handler._json = Mock()
                handler.do_GET()
                self.assertEqual(handler._json.call_args.args[0]["status"], "unsupported_location")
                self.assertEqual(handler._json.call_args.args[1], 404)
                handler.path = "/api/demo-prediction"
                handler._json = Mock()
                handler.do_GET()
                self.assertEqual(handler._json.call_args.args[0]["status"], "invalid_request")
                self.assertEqual(handler._json.call_args.args[1], 400)
                handler.path = "/api/river-level-prediction?station=alipingal-devi"
                handler._json = Mock()
                handler.do_GET()
                self.assertIsNone(handler._json.call_args.args[0]["predicted_level_24h_m"])
                self.assertEqual(handler._json.call_args.args[0]["status"], "forecast_unavailable")
                self.assertEqual(handler._json.call_args.args[1], 200)
            finally:
                service.close()

    def test_fresh_gauge_reading_gets_threshold_category_and_approximate_age(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            service.cwc_demo_record = {
                "station_name": "Alipingal / Devi test gauge",
                "latest_observation": {"observed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00"), "level_m": 11.0},
                "observation_24h_prior": None,
            }
            try:
                result = service.experimental_gauge_demo("alipingal-devi")
                self.assertEqual(result["freshness"], "fresh")
                self.assertEqual(result["risk_category"], "Warning level exceeded")
                self.assertEqual(result["age_days_approx"], 0)
            finally:
                service.close()

    def test_cached_real_observation_reports_stale_forecast_unavailable_and_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                result = service.river_level_prediction_demo("alipingal-devi")
                self.assertEqual(result["status"], "forecast_unavailable")
                self.assertEqual(result["latest_observation"]["observed_at"], "2024-05-09T04:00:00")
                self.assertEqual(result["latest_observation"]["gauge_level_m"], 4.001)
                self.assertEqual(result["latest_observation"]["freshness"], "stale")
                self.assertIsNone(result["predicted_level_24h_m"])
                self.assertEqual(result["model_evaluation"]["test_samples"], 28)
                self.assertGreater(result["model_evaluation"]["ridge_mae_m"],
                                   result["model_evaluation"]["persistence_mae_m"])
                handler_type = make_handler(service)
                handler = handler_type.__new__(handler_type)
                handler.path = "/api/river-level-prediction?station=alipingal-devi"
                handler._json = Mock()
                handler.do_GET()
                payload, status = handler._json.call_args.args
                self.assertEqual(status, 200)
                self.assertEqual(payload["status"], "forecast_unavailable")
                self.assertIsNone(payload["predicted_level_24h_m"])
            finally:
                service.close()

    def test_experimental_gauge_demo_rejects_unsupported_station(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                result = service.experimental_gauge_demo("chennai")
                self.assertEqual(result["status"], "unsupported_location")
                self.assertIsNone(result["risk_category"])
                self.assertIsNone(result["probability"])
            finally:
                service.close()

    def test_coordinate_validation_fails_for_out_of_range_location(self):
        with tempfile.TemporaryDirectory() as temp:
            service = FloodService(Path(temp), None, ROOT / "frontend")
            try:
                with self.assertRaisesRegex(ValueError, "latitude"):
                    service.query(91, 0)
                with self.assertRaisesRegex(ValueError, "longitude"):
                    service.query(0, 181)
            finally:
                service.close()

    def test_historical_reports_are_nearby_records_not_forecasts(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "events.csv"
            fields = ["event_id", "country", "admin1", "admin2", "event_date", "event_year",
                      "date_precision", "latitude", "longitude", "geocode_method"]
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow({"event_id": "real-record", "country": "Testland", "event_date": "2001-02-03",
                                 "event_year": "2001", "date_precision": "day", "latitude": "10.0",
                                 "longitude": "20.0", "geocode_method": "ADM2_EXACT"})
            index = HistoricalEventIndex(path)
            result = index.nearby(10.01, 20.01)
            self.assertEqual(result["status"], "available")
            self.assertEqual(result["nearby_report_count"], 1)
            self.assertEqual(result["results"][0]["event_id"], "real-record")
            self.assertEqual(result["results"][0]["latitude"], 10.0)
            self.assertIn("not exposure-normalized risk", result["interpretation"])
            unsupported = index.nearby(-20, -20)
            self.assertEqual(unsupported["status"], "no_nearby_records")
            self.assertIn("does not prove", unsupported["reason"])

    def test_partial_date_fields_are_not_fabricated(self):
        self.assertEqual(_date_parts("2012/07/00"), ("", "2012", "07", "month"))
        self.assertEqual(_date_parts("07/00/2012"), ("", "2012", "07", "month"))

    def test_real_cleaned_catalog_is_integrated_into_location_query(self):
        with tempfile.TemporaryDirectory() as temp:
            cleaned = ROOT / "outputs/flood_events/desinventar_cleaned.csv"
            self.assertTrue(cleaned.is_file())
            service = FloodService(Path(temp), None, ROOT / "frontend", cleaned)
            try:
                row = next(iter(next(iter(service.event_index.cells.values()))))
                result = service.query(row["_latitude"], row["_longitude"])
                self.assertEqual(result["status"], "partial")
                self.assertGreaterEqual(result["historical_event_reports"]["nearby_report_count"], 1)
                self.assertEqual(result["future_flood_event_prediction"]["probability"], None)
            finally:
                service.close()


if __name__ == "__main__":
    unittest.main()
