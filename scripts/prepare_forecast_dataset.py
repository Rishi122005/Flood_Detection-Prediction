#!/usr/bin/env python3
"""Label forecast snapshots only where event and observation coverage are documented."""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from forecasting.pipeline import DataError, prepare_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True, help="CSV using forecasting/templates/features.csv headers")
    parser.add_argument("--events", type=Path, required=True, help="Documented flood events CSV")
    parser.add_argument("--coverage", type=Path, required=True, help="Intervals with confirmed event surveillance")
    parser.add_argument("--glofas-export", type=Path,
                        help="optional output of scripts/export_glofas_point.py; aligned by location and issue/valid times")
    parser.add_argument("--output", type=Path, default=Path("outputs/forecasting/prepared_samples.csv"))
    parser.add_argument("--report", type=Path, default=Path("outputs/forecasting/preparation_report.json"))
    args = parser.parse_args()
    try:
        report = prepare_files(args.features, args.events, args.coverage, args.output, args.report,
                               args.glofas_export)
    except (DataError, OSError) as exc:
        parser.error(str(exc))
    print(f"{report['status']}: {report['labeled_rows']} labeled / {report['input_rows']} rows; report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
