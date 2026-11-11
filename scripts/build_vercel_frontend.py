"""Build the static dashboard with its public backend API URL configured."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    api_base_url = os.environ.get("API_BASE_URL", "").strip().rstrip("/")
    parsed = urlparse(api_base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
        raise SystemExit("Set API_BASE_URL to the HTTPS origin of the deployed backend")

    output = Path(os.environ.get("FLOOD_FRONTEND_OUTPUT_DIR", ROOT / "dist")).resolve()
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "frontend", output)
    config = f"window.FLOOD_API_BASE_URL = {json.dumps(api_base_url)};\n"
    (output / "assets" / "deployment-config.js").write_text(config, encoding="utf-8")
    print(f"Built static dashboard in {output} with backend {api_base_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
