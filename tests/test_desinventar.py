import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from forecasting.desinventar import NUMERIC_FIELDS, clean_desinventar


class DesInventarCleaningTests(unittest.TestCase):
    def test_cleaning_deduplicates_exact_rows_and_preserves_unknowns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "input.csv"
            fields = ["Country", "Adm1", "Adm2", "Date", "LAT", "LON",
                      "GEO_LAT", "GEO_LON", "GEO_METHOD", *NUMERIC_FIELDS]
            good = {name: "" for name in fields}
            good.update(Country="Example", Adm1="A", Adm2="B", Date="2012/07/00",
                        LAT="99999", LON="99999", GEO_LAT="10.5", GEO_LON="20.5",
                        GEO_METHOD="ADM2_EXACT", Deaths="0")
            bad = dict(good, Country="Bad", GEO_LAT="91")
            with source.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields)
                writer.writeheader()
                writer.writerow(good)
                writer.writerow(good)
                writer.writerow(bad)
            cleaned, report, bins = root / "clean.csv", root / "report.json", root / "bins.csv"
            result = clean_desinventar(source, cleaned, report, bins, today=date(2026, 1, 1))
            self.assertEqual(result["input_rows"], 3)
            self.assertEqual(result["usable_rows"], 1)
            self.assertEqual(result["exact_duplicate_rows_removed"], 1)
            self.assertEqual(result["invalid_geocoded_coordinates"], 1)
            with cleaned.open(newline="", encoding="utf-8") as stream:
                row = next(csv.DictReader(stream))
            self.assertEqual(row["event_date"], "")
            self.assertEqual(row["event_month"], "07")
            self.assertEqual(row["date_precision"], "month")
            self.assertEqual(row["impact_deaths"], "0")
            self.assertEqual(row["impact_injured"], "")
            with bins.open(newline="", encoding="utf-8") as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 1)


if __name__ == "__main__":
    unittest.main()
