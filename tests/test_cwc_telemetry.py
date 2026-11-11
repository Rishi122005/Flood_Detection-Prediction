import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from forecasting.cwc_telemetry import audit_cwc_csv, parse_observation_time


class CwcTelemetryAuditTests(unittest.TestCase):
    def make_csv(self, directory):
        path = Path(directory) / "telemetry.csv"
        headers = ["Station", "Agency", "District", "River", "Basin", "Latitude", "Longitude",
                   "Data Acquisition Time", "River Water Level Telemetry Hourly (meter)",
                   "RL_of_zeroGauge", "MeanSeaLevel"]
        rows = [
            ["Gauge A", "CWC", "District A", "River A", "Mahanadi", "20.0", "85.0", "01-01-2021 02:00", "5.0", "4.0", "4.0"],
            ["Gauge A", "CWC", "District A", "River A", "Mahanadi", "20.0", "85.0", "01-01-2021 00:00", "4.5", "4.0", "4.0"],
            ["Gauge A", "CWC", "District A", "River A", "Mahanadi", "20.0", "85.0", "01-01-2021 00:00", "4.5", "4.0", "4.0"],
            ["Gauge A", "CWC", "District A", "River A", "Mahanadi", "20.0", "85.0", "01-01-2021 03:00", "bad", "4.0", "4.0"],
        ]
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def test_audits_unordered_records_duplicates_gaps_and_bad_levels(self):
        with tempfile.TemporaryDirectory() as directory:
            result = audit_cwc_csv(self.make_csv(directory))
        self.assertEqual(result["record_count"], 4)
        self.assertEqual(result["station_count"], 1)
        self.assertFalse(result["rows_ordered_by_station_and_time"])
        self.assertEqual(result["invalid_water_level_rows"], 1)
        self.assertEqual(result["danger_or_warning_level_columns"], [])
        station = result["stations"][0]
        self.assertEqual(station["duplicate_timestamps"], 1)
        self.assertEqual(station["gap_intervals_over_1h"], 1)
        self.assertEqual(station["longest_interval_hours"], 2.0)
        self.assertEqual(station["valid_observations"], 3)
        self.assertEqual(station["expected_hourly_records_in_span"], 3)
        self.assertEqual(station["hourly_coverage_pct"], 66.667)
        self.assertEqual(station["coordinates"], [{"latitude": 20.0, "longitude": 85.0}])
        self.assertIsNone(parse_observation_time("01-01-2021 02:00").tzinfo)
        self.assertIn("not specified", result["timestamp_timezone"])

    def test_missing_file_fails_with_path(self):
        with self.assertRaisesRegex(FileNotFoundError, "not found"):
            audit_cwc_csv(Path("absent-cwc.csv"))

    def test_half_hour_samples_count_as_hourly_coverage_without_inflation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            headers = ["Station", "Agency", "District", "River", "Basin", "Latitude", "Longitude",
                       "Data Acquisition Time", "River Water Level Telemetry Hourly (meter)"]
            rows = [["Gauge A", "CWC", "District A", "River A", "Mahanadi", "20", "85", timestamp, "4.5"]
                    for timestamp in ("01-01-2021 00:00", "01-01-2021 00:30", "01-01-2021 01:00")]
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(headers)
                writer.writerows(rows)
            station = audit_cwc_csv(path)["stations"][0]
        self.assertEqual(station["hourly_coverage_pct"], 100.0)
        self.assertEqual(station["unique_recorded_hour_buckets"], 2)
        self.assertEqual(station["interval_cadence_counts"]["30-minute"], 2)


if __name__ == "__main__":
    unittest.main()
