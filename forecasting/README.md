# Future flood forecasting data contract

## Current status

This checkout supports retrospective SAR flood extent segmentation. It does not contain a validated future flood-event model. Official sources publish Alipingal/Devi thresholds (warning 10.85 m, danger 11.76 m, HFL 13.11 m), but local telemetry has unresolved readings above HFL, coordinate mismatch, major gaps, and no timezone declaration. See `reports/cwc_threshold_research.md`. Paired Sen1Floods11 masks label flood extent at acquisition time, not flood onset in a future period. The saved U-Net cannot forecast future floods.

The templates under `templates/` are intentionally header-only. No observations, event labels, or no-flood periods have been fabricated. A row is only labeled negative if surveillance coverage is documented continuously over the full 24-hour target window. Absence of an event record alone is not a negative label.

The local DesInventar catalogue (`data/floodevents/DesInventar_Geocoded.csv`) has been cleaned for historical lookups, but it is presence-only disaster reporting with post-event impacts and representative geocodes. It is not suitable by itself for supervised future flood-onset training. Use `python scripts/preprocess_flood_events.py` to regenerate the cleaned output and descriptive spatial record counts; neither output is a flood probability or an exposure-normalized risk surface.

## Required input

Populate `features.csv` with one timestamped forecast issue per location. Every feature must have a source and timestamp. Rainfall observation windows must be complete and available by `issued_at`; rainfall forecast vintages must have been issued by then and cover the full target window. River and reservoir measurements must also have been available by issue time. Timestamps must be ISO-8601 with a timezone. `evaluation_group` must identify an independent hydrometeorological event/location period and must not be reused across train/test boundaries.

The feature row also requires a GloFAS daily river-discharge forecast value and its issue/valid window. It is joined by exact `location_id`, using only a forecast issued by `issued_at` whose 24-hour valid interval covers the full target window. To populate it from the point export, pass `--glofas-export outputs/forecasting/glofas_point_forecast.csv` to the preparation command. A river-discharge feature is not an event label; event/coverage labels remain separately sourced.

Populate `events.csv` from documented flood onset records and `coverage.csv` from records that establish when flood surveillance was active. Include actual source URLs. These schemas are a preparation interface, not proof that any one agency provides data in this format.

For a live model query, populate exactly one row in `templates/prediction_features.csv`. This inference schema omits training-only IDs and labels but retains issue/valid timestamps and sources for every feature.

## Prepare, train, predict

From the repository root:

```bash
python -m pip install -r requirements-forecasting.txt
python scripts/export_glofas_point.py --scene data/S1GRDHand/India_25540_S1Hand.tif
python scripts/prepare_forecast_dataset.py \
  --features forecasting/templates/features.csv \
  --events forecasting/templates/events.csv \
  --coverage forecasting/templates/coverage.csv \
  --glofas-export outputs/forecasting/glofas_point_forecast.csv
python scripts/train_forecaster.py
python scripts/predict_future_flood.py --features forecasting/templates/prediction_features.csv
```

Preparation writes `outputs/forecasting/prepared_samples.csv` and `preparation_report.json`. The trainer requires at least 10 independent chronological groups and both labels in train, validation, and test, and refuses to overwrite an existing model. The test set is held out by whole group; threshold 0.5 is fixed. It compares logistic regression with a majority-class baseline determined from training data only. Scores are not operational warnings or calibrated probabilities. A real operational service requires additional calibration, external validation, monitoring, and warning thresholds approved by responsible authorities.

With the currently checked-in header-only templates, preparation produces zero labeled rows and training must not proceed. Prediction without a trained model exits with an unavailable status and does not emit a probability.

## Data acquisition status

The IMD API reference lists observed and forecast products. API endpoint checks during this project returned HTTP 401, and registration/API access requires credentials not available in the repository. The local CWC CSV is observed river water level (not a forecast). Official thresholds exist for Alipingal, while station identity/datum/timezone and extreme values still need quality confirmation. Document license, station/location identifiers, temporal cadence, issue/valid times, units, missingness, and geographic coverage for each source.

### Local CWC Mahanadi telemetry

The 148,640,758-byte file `data/observations/cwc_mahanadi_telemetry_2021_2025.csv` contains 921,203 records across 37 station keys from recorded dates 2021-01-01 through 2025-12-30. It includes station hierarchy, coordinates, `Data Acquisition Time`, `RL_of_zeroGauge`, `MeanSeaLevel`, and water level in metres, but no threshold columns. The streaming audit found 163 duplicate station/timestamp records, 53,848 gaps greater than one hour, 37 nonnumeric values, and 3 negative readings. **The source does not declare a timezone**; timestamps must not be called UTC. RAJIM has the highest recorded-hour coverage (76.122%) but a 2,077-hour longest gap and no station threshold was found for it. Official Alipingal/Devi warning, danger, and HFL levels are cited in the research report. Alipingal has 13,260 rows, 40.962% recorded-hour coverage, and a 4,313-hour longest gap; its local coordinates disagree with the CWC station table and 15 readings reach/exceed the published danger threshold, all above the listed HFL. Their provenance needs CWC clarification.

Run the reproducible but **diagnostic only** continuous-level pilot with:

```bash
python scripts/evaluate_cwc_level_forecast.py
```

It scans only the selected station into memory, applies the explicitly documented 0–13.11 m quality screen, uses exact past lags and an exact 24-hour target, splits by calendar year, and compares fixed Ridge with persistence. Results are saved under `reports/level_forecast_pilot.*`. The 2023 test has only 28 windows in a nearly constant low-stage range and Ridge loses to persistence. No model artifact is saved or deployed. This task predicts gauge level only, not flood risk.

Reproduce the audit with `python scripts/audit_cwc_telemetry.py`. It streams the CSV; if rows are not ordered by station/time, it creates a temporary SQLite index under the system temporary directory for exact duplicate, cadence, and gap statistics. It writes `reports/cwc_dataset_audit.md` and `.json`. The 24-hour event-onset training pipeline remains separate and still has zero prepared labels. No danger-level labels or water-level trend model have been created from this file.

## Local GloFAS data

The current local `data/glofas/data.grib` is an ECMWF hydrological river-discharge control-forecast GRIB2 file (60 records, 20 cycles in January 2025, with 24/48/72-hour leads). `data1.grib` is a two-record ECMWF analysis-type file for 2016-08-12/13 using a different local product template. Both use a 0.05° EPSG:4326 grid and have river-network masks. The forecast file is stale and the analysis file is not a discharge observation time series. Neither supplies observed flood event labels or warning thresholds. The exact local template semantics and GloFAS release version are not fully exposed by the installed GDAL driver; see `outputs/forecasting/glofas_inventory.json`.

GloFAS documentation states its gridded river network can differ from real-world river locations, recommends checking upstream catchment area, and warns of much higher uncertainty in small catchments. The local checkout has no matching upstream-area layer. Therefore the point query reports grid-cell distance and explicitly marks upstream area and site relevance unverified. CEMS terms provide free access subject to the service terms, require attribution when data are distributed, and state that these data are informational rather than an official warning. Consult the [CEMS terms](https://cds.climate.copernicus.eu/licences/cems-floods) before redistributing derived products.

Use `python scripts/inspect_glofas.py` to reproduce the inventory, and `python scripts/export_glofas_point.py --scene data/S1GRDHand/India_25540_S1Hand.tif` to export the actual forecasts nearest a georeferenced input scene. The CSV keeps forecast issue time, valid interval, lead, nearest-cell distance, discharge value and units. This is an external hydrological forecast, not a model-generated flood probability. It is not merged into onset-training rows because the available files lack the required matched historical inputs and event/coverage labels.

### Memory-safe access

Do not open this 60-record global file with `xarray/cfgrib` and then materialize the full dataset. Its nominal grid is 60 × 3,000 × 7,200 cells; a dense float64 cube alone is about 10.4 GB before masks, coordinates, decoder buffers, or copies. This exceeds the available 7.6 GiB RAM, especially with swap already exhausted. The reason for any particular earlier process termination was not independently reproduced, but full-cube materialization is sufficient to explain the memory risk. The `.idx` sidecar is retained; do not delete it as part of routine querying.

The supported reader uses Rasterio/GDAL to enumerate band metadata, then reads only a small nearest-cell search window and one pixel per forecast band. Avoid adding `src.read()` without a `window` to the GRIB path. Example bounded query:

```bash
python scripts/export_glofas_point.py --input data/glofas/data.grib \
  --coordinates 26.0094614103 92.5624068757 \
  --location-id India_25540_S1Hand \
  --output outputs/forecasting/glofas_point_forecast.csv
```

This sample location is the georeferenced SAR scene center, not an event-validated gauge location. The checked-in point-export CSV already contains one actual query (60 records); the data are stale after 2025-01-23 and do not support a current operational forecast.
