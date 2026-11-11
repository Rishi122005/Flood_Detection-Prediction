#!/usr/bin/env python3
"""Issue a 24-hour onset score only from a trained, validated forecast model."""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from forecasting.pipeline import FEATURES, PREDICTION_HEADERS, DataError, validate_feature_row


def unavailable_status() -> dict:
    """Return an explicit reason, reflecting whether local CWC levels exist."""
    cwc_path = ROOT / "data/observations/cwc_mahanadi_telemetry_2021_2025.csv"
    if cwc_path.is_file():
        reason = ("No trained and independently evaluated future flood-event model is present. Official sources list Alipingal/Devi warning 10.85 m, "
                  "danger 11.76 m, and historical HFL 13.11 m, but local telemetry has unresolved readings above HFL, a coordinate mismatch, "
                  "substantial gaps, and unspecified timestamp timezone. The small continuous level pilot is diagnostic only and worse than persistence; "
                  "it is not a flood prediction.")
        next_step = ("Obtain CWC-confirmed Alipingal station identity, datum, timezone and quality flags/corrections for values above HFL; then collect "
                     "a longer verified series with multiple threshold events and complete non-event windows for an independent chronological evaluation.")
    else:
        reason = "No trained and independently evaluated future flood forecasting model is present."
        next_step = ("Acquire station-matched timestamped predictors and verified flood/event labels plus complete non-event surveillance; "
                     "prepare chronological groups and pass the training evidence gates.")
    return {"status": "unavailable", "forecast": None, "reason": reason,
            "required_next_step": next_step}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", type=Path, required=True, help="one timestamped input row CSV")
    parser.add_argument("--model", type=Path, default=Path("models/flood_forecaster.joblib"))
    parser.add_argument("--output", type=Path, default=Path("outputs/forecasting/latest_prediction.json"))
    args = parser.parse_args()
    if not args.model.is_file():
        result = unavailable_status()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(result["reason"])
        print(f"Status written: {args.output}")
        return 2
    try:
        with args.features.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            missing = set(PREDICTION_HEADERS) - set(reader.fieldnames or [])
            if missing:
                raise DataError("prediction input missing columns: " + ", ".join(sorted(missing)))
            rows = list(reader)
            if len(rows) != 1:
                raise DataError("prediction input must contain exactly one feature row")
            row = rows[0]
        row.setdefault("sample_id", "inference")
        row.setdefault("evaluation_group", "inference")
        issued, target_end = validate_feature_row(row)
        import joblib
        artifact = joblib.load(args.model)
        if tuple(artifact.get("features", ())) != FEATURES or artifact.get("horizon_hours") != 24:
            raise DataError("model artifact feature schema or horizon does not match this pipeline")
        score = float(artifact["model"].predict_proba([[float(row[name]) for name in FEATURES]])[0, 1])
        result = {"status": "score_generated", "location_id": row["location_id"],
                  "issued_at": issued.isoformat(), "target_window_end": target_end.isoformat(),
                  "horizon_hours": 24, "model_score": score,
                  "interpretation": "Model score; it is not an operational warning or calibrated probability.",
                  "model_path": str(args.model)}
    except (OSError, ValueError, KeyError, ImportError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{result['status']}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
