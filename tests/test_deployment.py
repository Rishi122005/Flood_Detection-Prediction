from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.build_vercel_frontend import main as build_frontend


ROOT = Path(__file__).resolve().parents[1]


class DeploymentConfigTests(unittest.TestCase):
    def test_vercel_build_copies_dashboard_and_injects_https_backend_origin(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "static"
            with patch.dict(os.environ, {
                "API_BASE_URL": "https://flood-api.example.net/",
                "FLOOD_FRONTEND_OUTPUT_DIR": str(output),
            }, clear=False):
                self.assertEqual(build_frontend(), 0)
            config = (output / "assets/deployment-config.js").read_text(encoding="utf-8")
            self.assertIn('"https://flood-api.example.net"', config)
            self.assertTrue((output / "index.html").is_file())
            self.assertTrue((output / "assets/earth_texture.png").is_file())

    def test_vercel_build_rejects_missing_or_non_https_api_origin(self):
        for value in ("", "http://flood-api.example.net", "https://example.net/api"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temp:
                with patch.dict(os.environ, {
                    "API_BASE_URL": value,
                    "FLOOD_FRONTEND_OUTPUT_DIR": str(Path(temp) / "static"),
                }, clear=False):
                    with self.assertRaises(SystemExit):
                        build_frontend()

    def test_tflite_only_mode_does_not_import_tensorflow_or_convert_at_runtime(self):
        script = r'''
import os, sys, types
runtime = types.ModuleType("ai_edge_litert")
runtime.__path__ = []
interpreter = types.ModuleType("ai_edge_litert.interpreter")
class FakeInterpreter: pass
interpreter.Interpreter = FakeInterpreter
sys.modules["ai_edge_litert"] = runtime
sys.modules["ai_edge_litert.interpreter"] = interpreter
os.environ["FLOOD_TFLITE_RUNTIME_ONLY"] = "1"
from pathlib import Path
import scripts.predict_flood as prediction
assert prediction.tf is None
assert prediction.TFLITE_INTERPRETER is FakeInterpreter
try:
    prediction.load_tflite_model(Path("missing.keras"), Path("missing.tflite"))
except FileNotFoundError as exc:
    assert "cannot convert a Keras checkpoint at runtime" in str(exc)
else:
    raise AssertionError("TFLite-only mode must fail closed without its converted model")
print("TFLite-only runtime path passed")
'''
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, text=True,
                                capture_output=True, check=False, timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("TFLite-only runtime path passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
