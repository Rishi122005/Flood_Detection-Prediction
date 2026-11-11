import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from scripts.compare_before_after import compare


class BeforeAfterTests(unittest.TestCase):
    def test_change_classes_and_aligned_area_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            names = {
                "before": "before_2016-07-19_VV_VH",
                "after": "after_2016-08-12_VV_VH",
            }
            profile = dict(driver="GTiff", height=2, width=2, count=1, dtype="uint8",
                           crs="EPSG:4326", transform=from_origin(93, 27, .001, .001), nodata=255)
            for date_key, values in (("before", [[1, 0], [0, 1]]),
                                     ("after", [[1, 1], [0, 0]])):
                name = names[date_key]
                sub = root / "predictions" / date_key
                sub.mkdir(parents=True)
                with rasterio.open(sub / (name + "_mask.tif"), "w", **profile) as dst:
                    dst.write(np.array(values, dtype=np.uint8), 1)
                prob_profile = {**profile, "dtype": "float32", "nodata": -9999.0}
                with rasterio.open(sub / (name + "_probability.tif"), "w", **prob_profile) as dst:
                    dst.write(np.zeros((2, 2), dtype=np.float32), 1)
                img_profile = {**profile, "dtype": "float32", "nodata": -9999.0}
                with rasterio.open(root / (name + ".tif"), "w", **img_profile) as dst:
                    dst.write(np.full((2, 2), -15, dtype=np.float32), 1)
            result = compare(root)
            self.assertTrue(result["grid_aligned"])
            self.assertEqual(result["newly_segmented_pixels"], 1)
            self.assertEqual(result["receded_segmented_pixels"], 1)
            self.assertEqual(result["persistent_segmented_pixels"], 1)
            with rasterio.open(root / "change_mask.tif") as ds:
                self.assertEqual(ds.read(1).tolist(), [[3, 1], [0, 2]])
            self.assertTrue((root / "before_after_comparison.png").is_file())

    def test_rejects_pair_with_different_grid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for date_key, name, x_origin in (
                ("before", "before_2016-07-19_VV_VH", 93),
                ("after", "after_2016-08-12_VV_VH", 94),
            ):
                sub = root / "predictions" / date_key
                sub.mkdir(parents=True)
                profile = dict(driver="GTiff", height=2, width=2, count=1, dtype="uint8",
                               crs="EPSG:4326", transform=from_origin(x_origin, 27, .001, .001), nodata=255)
                with rasterio.open(sub / (name + "_mask.tif"), "w", **profile) as dst:
                    dst.write(np.zeros((2, 2), dtype=np.uint8), 1)
            with self.assertRaisesRegex(ValueError, "not exactly grid aligned"):
                compare(root)


if __name__ == "__main__":
    unittest.main()
