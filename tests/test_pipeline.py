"""Fast unit tests for preprocessing, tiling, geospatial area, and metrics."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_origin

from scripts.evaluate_model import metrics
from scripts.predict_flood import (TFLitePredictor, discover_india_scenes, normalize, pixel_area_m2,
                                   predict_array, run, tile_starts)


class ConstantModel:
    def __init__(self, value: float):
        self.value = value
        self.calls = 0
        self.input_shape = (None, 512, 512, 2)

    def predict(self, batch, verbose=0):
        self.calls += 1
        return np.full((batch.shape[0], 512, 512, 1), self.value, dtype=np.float32)


class PipelineTests(unittest.TestCase):
    def test_normalization_clips_and_zero_fills_invalid(self):
        vv = np.array([[-40, -15], [5, 0]], np.float32)
        vh = np.array([[-50, -20], [2, -5]], np.float32)
        valid = np.array([[True, True], [False, True]])
        actual = normalize(vv, vh, valid)
        self.assertEqual(actual.shape, (2, 2, 2))
        np.testing.assert_allclose(actual[0, 0], [0, 0])
        np.testing.assert_allclose(actual[0, 1], [.5, .5])
        np.testing.assert_allclose(actual[1, 0], [0, 0])
        np.testing.assert_allclose(actual[1, 1], [1, 1])
        self.assertTrue(np.isfinite(actual).all())

    def test_tiles_cover_edges_and_overlap(self):
        self.assertEqual(tile_starts(512, 512, 448), [0])
        self.assertEqual(tile_starts(600, 512, 448), [0, 88])
        result = predict_array(ConstantModel(.37), np.zeros((600, 700, 2), np.float32), tile=512, overlap=64)
        self.assertEqual(result.shape, (600, 700))
        np.testing.assert_allclose(result, .37, atol=1e-6)

    def test_one_model_call_for_one_512_pixel_scene(self):
        model = ConstantModel(.62)
        result = predict_array(model, np.zeros((512, 512, 2), np.float32), tile=512, overlap=64)
        self.assertEqual(model.calls, 1)
        self.assertEqual(result.shape, (512, 512))
        np.testing.assert_allclose(result, .62, atol=1e-6)

    def test_tflite_adapter_preserves_float32_batch_contract(self):
        with patch("scripts.predict_flood.tf.lite.Interpreter") as factory:
            engine = factory.return_value
            engine.get_input_details.return_value = [{"index": 3, "shape": np.array([1, 512, 512, 2]),
                                                       "dtype": np.float32}]
            engine.get_output_details.return_value = [{"index": 7, "shape": np.array([1, 512, 512, 1]),
                                                        "dtype": np.float32}]
            expected = np.full((1, 512, 512, 1), .25, dtype=np.float32)
            engine.get_tensor.return_value = expected
            predictor = TFLitePredictor(Path("cached.tflite"), threads=8)
            actual = predictor.predict(np.zeros((1, 512, 512, 2), dtype=np.float32))
            factory.assert_called_once_with(model_path="cached.tflite", num_threads=8)
            engine.allocate_tensors.assert_called_once()
            engine.set_tensor.assert_called_once()
            engine.invoke.assert_called_once()
            np.testing.assert_array_equal(actual, expected)

    def test_fresh_run_writes_probability_mask_overlay_and_area_summary(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            image_path, output_dir = root / "synthetic.tif", root / "out"
            profile = {"driver": "GTiff", "height": 512, "width": 512, "count": 2,
                       "dtype": "float32", "crs": "EPSG:3857",
                       "transform": from_origin(0, 5120, 10, 10)}
            with rasterio.open(image_path, "w", **profile) as dst:
                dst.write(np.full((512, 512), -15, dtype=np.float32), 1)
                dst.write(np.full((512, 512), -20, dtype=np.float32), 2)
                dst.set_band_description(1, "VV")
                dst.set_band_description(2, "VH")
            result = run(image_path, Path("saved.keras"), output_dir, .5, 512, 64,
                         model=ConstantModel(.8))
            self.assertEqual(result["predicted_flood_pixels"], 512 * 512)
            self.assertAlmostEqual(result["predicted_flood_percent_valid"], 100.0)
            self.assertAlmostEqual(result["predicted_flood_area_km2"], 26.2144, places=5)
            for suffix in ("_probability.tif", "_mask.tif", "_prediction.png", "_summary.json"):
                self.assertTrue((output_dir / f"synthetic{suffix}").is_file())

    def test_overlap_validation(self):
        with self.assertRaises(ValueError):
            predict_array(ConstantModel(.5), np.zeros((2, 2, 2), np.float32), tile=512, overlap=512)

    def test_projected_pixel_area_uses_affine_units(self):
        areas = pixel_area_m2(from_origin(0, 100, 10, 10), CRS.from_epsg(3857), 2, 3)
        np.testing.assert_allclose(areas, [100, 100])

    def test_geographic_pixel_area_uses_equal_area_projection(self):
        areas = pixel_area_m2(from_origin(80, 20, .0001, .0001), CRS.from_epsg(4326), 2, 3)
        self.assertEqual(areas.shape, (2,))
        self.assertTrue(np.isfinite(areas).all())
        self.assertTrue(np.all(areas > 50) and np.all(areas < 150))

    def test_metrics_and_zero_denominators(self):
        result = metrics(np.array([True, False, True]), np.array([True, True, False]))
        self.assertEqual((result["tp"], result["tn"], result["fp"], result["fn"]), (1, 0, 1, 1))
        self.assertAlmostEqual(result["f1_dice"], .5)
        empty = metrics(np.zeros(3, bool), np.zeros(3, bool))
        self.assertEqual(empty["precision"], 0)
        self.assertEqual(empty["specificity"], 1)

    def test_india_discovery_finds_compatible_local_scenes(self):
        from pathlib import Path
        root = Path(__file__).resolve().parents[1]
        scenes = discover_india_scenes(root / "data")
        self.assertTrue(scenes)
        self.assertTrue(all("india" in path.name.casefold() for path in scenes))


if __name__ == "__main__":
    unittest.main()
