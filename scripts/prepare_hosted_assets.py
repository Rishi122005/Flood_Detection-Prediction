"""Compact scene preview PNGs into WebP inside a deployment image only."""
from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PREDICTIONS = ROOT / "outputs/india/predictions"


def main() -> int:
    converted = 0
    saved = 0
    for source in sorted(PREDICTIONS.glob("*_prediction.png")):
        target = source.with_suffix(".webp")
        with Image.open(source) as image:
            image.save(target, "WEBP", quality=88, method=5)
        converted += 1
        if target.stat().st_size < source.stat().st_size:
            source.unlink()
            saved += 1
        else:
            target.unlink()
    print(f"Prepared {converted} scene previews; compacted {saved} for deployment")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
