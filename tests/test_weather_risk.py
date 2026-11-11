import unittest
from datetime import datetime
from urllib.parse import parse_qs, urlparse
from urllib.error import URLError
from zoneinfo import ZoneInfo
from unittest.mock import patch

from src.flood_app.weather_service import (
    INDIA_LOCATIONS, OpenMeteoWeatherService, WeatherServiceError,
    assess_rainfall_risk, build_weather_result, validate_coordinates,
)


def sample_response(precipitation=None, probability=None):
    start = datetime(2026, 11, 10, 23, tzinfo=ZoneInfo("Asia/Kolkata"))
    from datetime import timedelta
    times = [(start + timedelta(hours=i)).replace(tzinfo=None).isoformat(timespec="minutes") for i in range(48)]
    return {
        "latitude": 26.125, "longitude": 91.75, "elevation": 55,
        "timezone": "Asia/Kolkata",
        "current": {"time": "2026-11-11T00:30", "temperature_2m": 22.5,
                    "relative_humidity_2m": 74, "wind_speed_10m": 8.2, "weather_code": 2},
        "hourly": {
            "time": times,
            "precipitation": precipitation if precipitation is not None else [0.2] * 48,
            "precipitation_probability": probability if probability is not None else [10] * 48,
            "temperature_2m": [22.0] * 48, "relative_humidity_2m": [75] * 48,
            "wind_speed_10m": [8.0] * 48, "weather_code": [2] * 48,
        },
    }


class WeatherRiskTests(unittest.TestCase):
    def test_required_indian_locations_and_coordinate_validation(self):
        locations = {item["id"]: item for item in INDIA_LOCATIONS}
        self.assertEqual(len(locations), 10)
        self.assertEqual((locations["guwahati"]["latitude"], locations["guwahati"]["longitude"]), (26.1445, 91.7362))
        self.assertEqual((locations["chennai"]["latitude"], locations["chennai"]["longitude"]), (13.0827, 80.2707))
        self.assertEqual((locations["patna"]["latitude"], locations["patna"]["longitude"]), (25.5941, 85.1376))
        self.assertEqual(validate_coordinates(-90, 180), (-90.0, 180.0))
        with self.assertRaisesRegex(ValueError, "latitude"):
            validate_coordinates(90.01, 0)
        with self.assertRaisesRegex(ValueError, "longitude"):
            validate_coordinates(0, 180.01)
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_coordinates(float("nan"), 0)

    def test_risk_engine_low_moderate_high_and_missing_inputs(self):
        low = assess_rainfall_risk(3, 24, 4, 20, 24)
        moderate = assess_rainfall_risk(16, 35, 10, 30, 24)
        high = assess_rainfall_risk(2, 42, 31, 65, 24)
        mismatched_probability = assess_rainfall_risk(2, 42, 31, 80, 24, probability_at_max_hourly_pct=10)
        self.assertEqual(low["level"], "LOW")
        self.assertEqual(moderate["level"], "MODERATE")
        self.assertEqual(high["level"], "HIGH")
        self.assertEqual(mismatched_probability["level"], "LOW")
        self.assertTrue(any("31.0 mm" in reason for reason in high["reasons"]))
        missing = assess_rainfall_risk(None, 10, 1, 10, 24)
        incomplete = assess_rainfall_risk(1, 10, 1, 10, 23)
        self.assertEqual(missing["status"], "insufficient_data")
        self.assertEqual(missing["message"], "Insufficient weather data for risk assessment.")
        self.assertEqual(incomplete["status"], "insufficient_data")

    def test_three_hour_and_24_hour_rainfall_use_only_future_entries(self):
        raw = sample_response()
        raw["hourly"]["precipitation"] = [99, 88] + [float(i % 4) for i in range(46)]
        raw["hourly"]["precipitation_probability"] = [99, 98] + [20] * 46
        result = build_weather_result(raw, 26.1445, 91.7362, "Guwahati, Assam", "2026-11-10T19:00:00+00:00")
        rows = result["hourly_forecast_next_24h"]
        self.assertEqual(len(rows), 24)
        expected = raw["hourly"]["precipitation"][2:5]
        self.assertEqual(result["rainfall"]["next_3h_mm"], sum(expected))
        self.assertEqual(result["rainfall"]["next_24h_mm"], sum(raw["hourly"]["precipitation"][2:26]))
        self.assertEqual(result["rainfall"]["maximum_hourly_mm"], max(raw["hourly"]["precipitation"][2:26]))
        self.assertEqual(result["rainfall"]["maximum_precipitation_probability_pct"], 20)
        self.assertEqual(result["risk_assessment"]["level"], "LOW")
        self.assertEqual(result["timezone"], "Asia/Kolkata")
        self.assertEqual(result["source"]["provider"], "Open-Meteo")
        self.assertEqual(result["location"]["name"], "Guwahati, Assam")

    def test_missing_hourly_values_fail_closed(self):
        raw = sample_response()
        raw["hourly"]["precipitation"][5] = None
        result = build_weather_result(raw, 25.5941, 85.1376, "Patna, Bihar")
        self.assertIsNone(result["rainfall"]["next_24h_mm"])
        self.assertEqual(result["risk_assessment"]["status"], "insufficient_data")
        self.assertIsNone(result["risk_assessment"]["level"])

    def test_empty_and_api_error_responses_are_errors_not_fabricated_values(self):
        with self.assertRaisesRegex(WeatherServiceError, "no hourly forecast"):
            build_weather_result({"timezone": "Asia/Kolkata", "hourly": {"time": []}}, 10, 10, "test")
        with self.assertRaisesRegex(WeatherServiceError, "unavailable"):
            build_weather_result({"error": True, "reason": "bad coordinates"}, 10, 10, "test")
        with patch("src.flood_app.weather_service.urlopen", side_effect=URLError("offline")):
            from src.flood_app.weather_service import _open_meteo_json
            with self.assertRaisesRegex(WeatherServiceError, "Could not retrieve Open-Meteo"):
                _open_meteo_json("https://api.open-meteo.com/v1/forecast", 1)

    def test_weather_service_builds_real_api_query_handles_failure_and_cache(self):
        calls = []
        def transport(url, timeout):
            calls.append((url, timeout))
            return sample_response()
        service = OpenMeteoWeatherService(transport=transport)
        first = service.get_forecast(13.0827, 80.2707, "Chennai, Tamil Nadu")
        parsed = parse_qs(urlparse(calls[0][0]).query)
        self.assertEqual(parsed["timezone"], ["Asia/Kolkata"])
        self.assertEqual(parsed["forecast_days"], ["2"])
        self.assertIn("precipitation_probability", parsed["hourly"][0])
        self.assertIn("temperature_2m", parsed["current"][0])
        self.assertFalse(first["cache_hit"])
        cached = service.get_forecast(13.0827, 80.2707, "Manual coordinates")
        self.assertTrue(cached["cache_hit"])
        self.assertEqual(cached["location"]["name"], "Manual coordinates")
        self.assertEqual(len(calls), 1)
        service.get_forecast(13.0827, 80.2707, "Chennai", force_refresh=True)
        self.assertEqual(len(calls), 2)
        with self.assertRaisesRegex(ValueError, "latitude"):
            service.get_forecast(91, 80)
        failing = OpenMeteoWeatherService(transport=lambda _url, _timeout: (_ for _ in ()).throw(WeatherServiceError("network timeout")))
        with self.assertRaisesRegex(WeatherServiceError, "network timeout"):
            failing.get_forecast(26.1445, 91.7362)


if __name__ == "__main__":
    unittest.main()
