import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from forecasting.cwc_level_pilot import evaluate, make_examples


class CwcLevelPilotTests(unittest.TestCase):
    def test_examples_use_only_past_lags_and_exact_future_24h_target(self):
        start = datetime(2021, 1, 1)
        series = {start + timedelta(hours=i): 4.0 + i / 1000 for i in range(100)}
        examples = make_examples(series)
        first = examples[0]
        self.assertEqual(first["issued_at"], start + timedelta(hours=24))
        self.assertEqual(first["target_at"], first["issued_at"] + timedelta(hours=24))
        self.assertTrue(np.allclose(first["features"], [4.024, .001, .006, .024]))

    def test_missing_lag_or_target_prevents_example(self):
        start = datetime(2021, 1, 1)
        series = {start + timedelta(hours=i): 4.0 for i in range(60)}
        del series[start + timedelta(hours=30)]
        examples = make_examples(series)
        self.assertNotIn(start + timedelta(hours=30), [e["issued_at"] for e in examples])

    def test_chronological_pilot_is_labeled_diagnostic_and_saves_no_model(self):
        start = datetime(2021, 1, 1)
        series = {start + timedelta(hours=i): 4.0 + (i % 7) * .001 for i in range(3 * 365 * 24)}
        result = evaluate(series)
        self.assertEqual(result["status"], "diagnostic_only")
        self.assertTrue(result["not_a_flood_prediction"])
        self.assertFalse(result["model_artifact_saved"])
        self.assertEqual(result["test_year"], 2023)
        self.assertIn("persistence", result)
        self.assertIn("ridge", result)


if __name__ == "__main__":
    unittest.main()
