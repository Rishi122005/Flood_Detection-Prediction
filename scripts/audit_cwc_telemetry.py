#!/usr/bin/env python3
"""Audit the local CWC Mahanadi hourly telemetry CSV using bounded memory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.cwc_telemetry import audit_cwc_csv, render_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path,
                        default=ROOT / "data/observations/cwc_mahanadi_telemetry_2021_2025.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/cwc_dataset_audit.json")
    parser.add_argument("--markdown", type=Path, default=ROOT / "reports/cwc_dataset_audit.md")
    args = parser.parse_args()
    try:
        result = audit_cwc_csv(args.input)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        import json
        args.report.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(render_markdown(result), encoding="utf-8")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Audited {result['record_count']:,} rows across {result['station_count']} stations")
    print(f"Threshold columns: {result['danger_or_warning_level_columns'] or 'none'}")
    print(f"Markdown report: {args.markdown}")
    print(f"Machine-readable report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
