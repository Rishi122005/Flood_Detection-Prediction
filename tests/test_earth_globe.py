import json
import unittest
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


class EarthGlobeAssetTests(unittest.TestCase):
    def test_bundled_natural_earth_source_and_texture_are_local(self):
        source = ROOT / "frontend/earth_countries.geojson"
        texture = ROOT / "frontend/assets/earth_texture.png"
        source_data = json.loads(source.read_text(encoding="utf-8"))
        self.assertEqual(source_data["type"], "FeatureCollection")
        self.assertEqual(len(source_data["features"]), 177)
        with Image.open(texture) as image:
            self.assertEqual(image.size, (1440, 720))
            self.assertEqual(image.mode, "RGB")

    def test_dashboard_uses_local_geographical_texture_and_map_controls(self):
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        self.assertIn("/assets/earth_texture.png", html)
        self.assertIn("zoom-in", html)
        self.assertIn("go-chennai", html)
        self.assertIn("function selectChennai()", html)
        self.assertIn("state.zoom=6", html)
        self.assertIn("reset-globe", html)
        self.assertIn("Nearby historical flood-event reports", html)
        self.assertIn("map-caption", html)
        self.assertIn("lon:78.9629,lat:20.5937", html)
        self.assertIn("Math.min(12,value)", html)

    def test_india_location_selector_uses_coverage_and_query_apis(self):
        html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
        self.assertIn('id="india-location"', html)
        self.assertIn("fetchJson('/api/india-locations')", html)
        self.assertIn("fetchJson('/api/health')", html)
        self.assertIn("expectedApiVersion='india-location-demo-6'", html)
        self.assertIn("function clusterDetections", html)
        self.assertIn("currently visible records", html)
        self.assertIn("Scene centers are not flood locations", html)
        self.assertIn("stopImmediatePropagation", html)
        self.assertIn("id=\"demo-form\"", html)
        self.assertIn("/api/demo-prediction?station=", html)
        self.assertIn("actual forecast horizon: unavailable", html)
        self.assertIn("24-Hour Prediction Demo", html)
        self.assertIn("Predict Next 24 Hours", html)
        self.assertIn("/api/river-level-prediction?station=", html)
        self.assertIn("cache:'no-store'", html)
        self.assertIn("coverage_status==='supported'", html)
        self.assertIn("/api/query?lat=", html)
        self.assertIn("Probability: unavailable", html)


if __name__ == "__main__":
    unittest.main()
