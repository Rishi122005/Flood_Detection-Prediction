import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
from rasterio.crs import CRS
from rasterio.transform import Affine

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecasting.pipeline import DataError, FEATURES, align_glofas_forecasts, prepare_rows, validate_feature_row
from forecasting.glofas import _product_valid_time, extract_discharge_forecasts, haversine_km
from scripts.train_forecaster import chronological_group_split


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def base_row():
    issue = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return {
        "sample_id": "s1", "location_id": "basin-1", "evaluation_group": "event-1",
        "issued_at": iso(issue), "rainfall_observed_24h_mm": "12.5",
        "rainfall_observed_24h_start": iso(issue - timedelta(hours=24)),
        "rainfall_observed_24h_end": iso(issue),
        "rainfall_observed_available_at": iso(issue), "rainfall_observed_source": "station-record",
        "rainfall_forecast_24h_mm": "20", "rainfall_forecast_issue_at": iso(issue),
        "rainfall_forecast_valid_start": iso(issue),
        "rainfall_forecast_valid_end": iso(issue + timedelta(hours=24)),
        "rainfall_forecast_source": "forecast-vintage", "river_level_m": "2.1",
        "glofas_forecast_issue_at": iso(issue),
        "glofas_forecast_valid_start": iso(issue),
        "glofas_forecast_valid_end": iso(issue + timedelta(hours=24)),
        "glofas_forecast_source": "local-grib-export",
        "glofas_discharge_forecast_24h_m3_s": "12.0",
        "river_level_observed_at": iso(issue), "river_level_source": "gauge-record",
        "river_danger_level_m": "3.0", "reservoir_storage_mcm": "8.5",
        "reservoir_observed_at": iso(issue), "reservoir_source": "reservoir-record",
    }


class ForecastPreparationTests(unittest.TestCase):
    def test_valid_timestamped_row_and_feature_values(self):
        issue, end = validate_feature_row(base_row())
        self.assertEqual(end - issue, timedelta(hours=24))
        self.assertEqual(len(FEATURES), 6)

    def test_rejects_timezone_naive_or_future_information(self):
        row = base_row()
        row["issued_at"] = "2024-01-02T00:00:00"
        with self.assertRaisesRegex(DataError, "timezone"):
            validate_feature_row(row)
        row = base_row()
        issue = datetime(2024, 1, 2, tzinfo=timezone.utc)
        row["rainfall_forecast_issue_at"] = iso(issue + timedelta(minutes=1))
        with self.assertRaisesRegex(DataError, "issued by issue time"):
            validate_feature_row(row)

    def test_rejects_missing_and_nonfinite_features(self):
        row = base_row()
        row["river_level_m"] = "NaN"
        with self.assertRaisesRegex(DataError, "finite"):
            validate_feature_row(row)

    def test_labels_only_documented_onset_and_verified_negatives(self):
        row = base_row()
        issue = datetime(2024, 1, 2, tzinfo=timezone.utc)
        event = {"event_id": "f1", "location_id": "basin-1",
                 "event_start": iso(issue + timedelta(hours=12)),
                 "event_end": iso(issue + timedelta(hours=20)),
                 "source": "agency bulletin", "source_url": "https://example.test/event"}
        no_coverage = []
        labeled, report = prepare_rows([row], [event], no_coverage)
        self.assertEqual(labeled[0]["label_flood_onset_within_24h"], "1")
        self.assertEqual(report["positive_rows"], 1)

        row["sample_id"] = "s2"
        coverage = [{"location_id": "basin-1", "coverage_start": iso(issue),
                     "coverage_end": iso(issue + timedelta(hours=24)), "source": "agency log",
                     "source_url": "https://example.test/coverage", "coverage_notes": "complete"}]
        labeled, _ = prepare_rows([row], [], coverage)
        self.assertEqual(labeled[0]["label_flood_onset_within_24h"], "0")
        labeled, report = prepare_rows([row], [], [])
        self.assertEqual(labeled, [])
        self.assertEqual(report["unlabeled_or_invalid_rows"], 1)

    def test_glofas_alignment_uses_only_asof_records_covering_target(self):
        row = base_row()
        issue = datetime(2024, 1, 2, tzinfo=timezone.utc)
        forecast = {"location_id": row["location_id"], "forecast_issued_at": iso(issue),
                    "valid_from": iso(issue), "valid_until": iso(issue + timedelta(hours=24)),
                    "forecast_horizon_hours": "24", "river_discharge_m3_s": "18.75",
                    "unit": "m3 s-1", "record_type": "ECMWF control forecast", "source_file": "forecast.grib"}
        aligned = align_glofas_forecasts([row], [forecast])[0]
        self.assertEqual(aligned["glofas_discharge_forecast_24h_m3_s"], "18.75")
        future = dict(forecast, forecast_issued_at=iso(issue + timedelta(minutes=1)))
        aligned = align_glofas_forecasts([row], [future])[0]
        self.assertEqual(aligned["glofas_forecast_source"], "")


class ForecastTrainingGateTests(unittest.TestCase):
    def test_grouped_chronological_split_has_no_group_leakage(self):
        rows = []
        for i in range(10):
            for label in (0, 1):
                rows.append({"evaluation_group": f"g{i}",
                             "issued_at": iso(datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)),
                             "label_flood_onset_within_24h": str(label)})
        train, validation, test = chronological_group_split(rows)
        groups = [{r["evaluation_group"] for r in p} for p in (train, validation, test)]
        self.assertFalse(groups[0] & groups[1] or groups[0] & groups[2] or groups[1] & groups[2])
        self.assertTrue(all({r["label_flood_onset_within_24h"] for r in p} == {"0", "1"}
                            for p in (train, validation, test)))

    def test_small_dataset_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "at least 10 independent"):
            chronological_group_split([{"evaluation_group": "one", "issued_at": iso(datetime.now(timezone.utc)),
                                        "label_flood_onset_within_24h": "1"}])

    def test_no_model_prediction_emits_no_probability(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "status.json"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/predict_future_flood.py"),
                                     "--features", "missing.csv", "--model", str(Path(directory) / "absent.joblib"),
                                     "--output", str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            payload = json.loads(out.read_text())
            self.assertEqual(payload["status"], "unavailable")
            self.assertIsNone(payload["forecast"])
            self.assertIn("Official sources list Alipingal/Devi", payload["reason"])
            self.assertIn("danger 11.76 m", payload["reason"])
            self.assertIn("unresolved readings above HFL", payload["reason"])


class GlofasMetadataTests(unittest.TestCase):
    def test_local_product_template_dates_are_parsed_without_guessing_other_templates(self):
        pdt73 = "0 7 0 158 0 98 5 4 21 5 0 0 0 1 0 0 0 24 1 255 255 255 255 255 255 255 255 255 255 255 0 0 51 7 233 1 3 0 0 0 1 0 0 0 0 0 2 1 0 0 0 24 255 0 0 0 0"
        pdt72 = "0 7 255 253 0 98 5 9 147 41 255 255 255 1 0 0 0 0 1 255 255 255 255 255 255 255 255 255 255 255 7 224 8 13 0 0 0 1 0 0 0 0 0 2 1 0 0 0 24 255 0 0 0 0"
        self.assertEqual(_product_valid_time(pdt73, 73).isoformat(), "2025-01-03T00:00:00+00:00")
        self.assertEqual(_product_valid_time(pdt72, 72).isoformat(), "2016-08-13T00:00:00+00:00")
        self.assertIsNone(_product_valid_time(pdt73, 0))

    def test_haversine_distance_is_finite_and_symmetric(self):
        self.assertAlmostEqual(haversine_km(0, 0, 0, 1), haversine_km(0, 1, 0, 0), places=8)
        self.assertGreater(haversine_km(0, 0, 0, 1), 100)

    def test_forecast_extraction_only_reads_bounded_windows(self):
        class WindowOnlyDataset:
            width = height = 40
            nodata = 9999.0
            crs = CRS.from_epsg(4326)
            transform = Affine(0.05, 0, -1.0, 0, -0.05, 1.0)

            def __init__(self):
                self.read_windows = []

            def index(self, longitude, latitude):
                return 20, 20

            def xy(self, row, col):
                x, y = self.transform @ (col + 0.5, row + 0.5)
                return x, y

            def read(self, band, window=None, masked=False):
                if window is None:
                    raise AssertionError("GRIB value reads must specify a bounded window")
                self.read_windows.append(window)
                shape = (int(window.height), int(window.width))
                return np.ma.array(np.full(shape, 12.0), mask=np.zeros(shape, dtype=bool))

        dataset = WindowOnlyDataset()
        issued = datetime(2025, 1, 1, tzinfo=timezone.utc)
        records = [(1, issued, issued + timedelta(hours=24), {})]
        with patch("forecasting.glofas._forecast_records", return_value=records):
            forecasts, metadata = extract_discharge_forecasts(dataset, 0.0, 0.0)
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0]["river_discharge_m3_s"], 12.0)
        self.assertEqual(metadata["records"], 1)
        self.assertTrue(dataset.read_windows)
        self.assertTrue(all(int(window.width) < dataset.width and int(window.height) < dataset.height
                            for window in dataset.read_windows))
        self.assertEqual((int(dataset.read_windows[-1].width), int(dataset.read_windows[-1].height)), (1, 1))


if __name__ == "__main__":
    unittest.main()
