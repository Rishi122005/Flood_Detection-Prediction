# Global Flood Monitoring and Prediction Using Satellite Data

## Downloading the complete project assets

The primary U-Net checkpoint and large source rasters, GRIB files, and CWC telemetry are stored with Git LFS. Install Git LFS before cloning so those files are downloaded rather than leaving pointer files in the working tree:

```powershell
git lfs install
git clone https://github.com/Rishi122005/Flood_Detection-Prediction.git
cd Flood_Detection-Prediction
git lfs pull
```

The required `models/best_unet_flood.keras` checkpoint is included through Git LFS. Duplicate backup snapshots, generated upload results, and the derived TFLite cache are not included; the saved checkpoint can recreate the TFLite cache locally.

## Current verified dashboard status (2026-11-11)

The existing dark dashboard and interactive globe are preserved. The local API reports 68 georeferenced satellite scene records; all 68 have valid unique footprint-center coordinates. At the default globe scale their projected centers overlap heavily, so the UI draws count-labelled clusters and scene-ID list selection rather than implying one glyph equals one detection. These are scene footprints with model outputs, not 68 confirmed flood events.

The satellite upload path accepts the model-compatible two-band Sentinel-1 VV/VH GeoTIFF, writes a separate timestamped output directory, and returns fresh inference outputs and stage timings. Before/after analysis uses the existing aligned 2016 orbit-77 pair and is explicitly exploratory. The local GloFAS archive is stale and is never shown as a current 24-hour forecast. The latest CWC Alipingal record is historical/stale; its threshold display is not a forecast. Future flood-event prediction remains unavailable: available time-series data do not support an independently evaluated event forecast.

Architecture: `frontend/index.html` is the no-build dashboard; `scripts/run_server.py` starts the HTTP service in `src/flood_app/server.py`; `flood_pipeline/` contains model loading, SAR preprocessing, tiled inference, geospatial area accounting and artifact writing; `forecasting/` contains GloFAS/CWC/event-data preparation and guarded forecast experiments; `data/` contains benchmark imagery, masks, telemetry and local hydrology inputs; `models/` contains preserved checkpoints; `outputs/` contains existing results and timestamped fresh runs; `tests/` holds unit and service regression tests.

## Experimental weather-based flood-risk screening

The independent **AI Weather-Based Flood Risk Assessment** dashboard section retrieves current conditions and 48 hourly values from the free Open-Meteo Forecast API. Backend routes are `/api/weather-risk/locations` and `/api/weather-risk?city=guwahati` (or `?lat=...&lon=...` for manual coordinates); set `refresh=1` to bypass the short in-memory cache. Requests ask for hourly precipitation, precipitation probability, temperature, humidity, wind, WMO weather code, current weather, `Asia/Kolkata`, and two forecast days. Results identify both the selected coordinate and Open-Meteo weather-grid coordinate, including their separation. Retrieval time is UTC; the upstream response does not supply a model issue time, so none is claimed.

The displayed 3-hour and 24-hour precipitation values are sums of the next 3 and 24 valid hourly precipitation values after the API's current time. Maximum hourly rainfall and maximum precipitation probability are taken from that same next-24-hour window. Fewer than 24 complete hourly rainfall and precipitation-probability inputs produce `Insufficient weather data for risk assessment.`; missing values are never treated as zero.

The transparent, configurable prototype rules are defined in `src/flood_app/weather_service.py`. **HIGH** is triggered by at least 50 mm/3 h, at least 100 mm/24 h, or at least 30 mm in the maximum-rainfall hour when precipitation probability for that same hour is at least 60%. **MODERATE** is triggered by at least 15 mm/3 h, at least 50 mm/24 h, or at least 15 mm in the maximum-rainfall hour when precipitation probability for that same hour is at least 50%. HIGH takes precedence; otherwise complete inputs below all triggers are LOW. These are deliberately labeled prototype screening thresholds, not thresholds validated for a specific Indian basin or official warning levels. Precipitation probability describes precipitation likelihood, not flood probability. The output does not model river levels, drainage, soil moisture, terrain, or inundation and is not a trained or validated AI flood forecast. Network/API errors return an unavailable response without fallback values.

Automated weather tests use controlled mock responses only in unit tests; browser demonstration calls the live Open-Meteo service. The supported city list and experimental status are included in the API/UI, and manual coordinates are range checked.

Windows PowerShell startup for the weather-enabled version: `.venv\Scripts\python.exe scripts\run_server.py --host 127.0.0.1 --port 8005`, then open `http://127.0.0.1:8005/` (ports 8001–8004 may still host older dashboard processes). Run tests with `.venv\Scripts\python.exe -m unittest discover -s tests -v`. Optional real-browser smoke test: `$env:FLOOD_TEST_PORT='8005'; node scripts\verify_dashboard_browser.cjs` (requires Edge/Chrome and a running server).

This repository contains two separate workflows: Sentinel-1 SAR flood extent segmentation, and guarded future-onset forecasting data preparation. A local HTTP service and interactive coordinate globe display only georeferenced local predictions and supported hydrological source data; no frontend build tool or external web service is required.

## Problem and objectives

Flood extent can be mapped from Sentinel-1 synthetic aperture radar (SAR) imagery when optical imagery is affected by clouds. This project explores pixel-level flood segmentation from VV and VH backscatter. Its objectives are to prepare paired SAR and flood-mask samples, train/evaluate a U-Net, produce georeferenced probability and binary maps, and report performance only where a matching reference mask exists.

## Data in this checkout

`data/` contains Sen1Floods11 products organized into `S1GRDHand`, `LabelHand`, `S1OtsuLabelHand`, `JRCWaterHand`, `S2L1CHand`, and `CopernicusDEM`. There are 446 files in each of these six benchmark directories. SAR files are 2-band GeoTIFFs (VV then VH); labels use `-1` for unknown, `0` for non-flood, and `1` for flood. Official text split lists are in `splits/`. Dataset names include several regions/countries, including India. This is a benchmark subset, not nationwide India coverage.

The separate `data/vijayawada_sar/` directory is empty in this checkout. Therefore there is no local imagery supporting the notebook's Vijayawada September 2024 analysis. Existing figures and result files are historical artifacts; they are not represented here as independently reproduced results.

## Model and preprocessing

The preserved model is `models/best_unet_flood.keras` (backup: `models/best_unet_flood_backup.keras`). It loads with TensorFlow 2.21, expects `(512, 512, 2)`, returns `(512, 512, 1)`, and has 31,401,921 Keras parameters. The checkpoint also stores optimizer slots, so summing all HDF5 datasets overcounts model parameters. Preprocessing follows the notebook's fixed clipping and scaling: VV `[-30, 0] dB` and VH `[-35, -5] dB`, independently mapped to `[0, 1]`; channel order is VV, VH. Invalid input pixels are zero-filled for inference and excluded from reported counts. The default probability threshold is 0.5. On native Windows TensorFlow 2.21 reports CPU only; the CLI uses a cached float32 TFLite conversion and XNNPACK CPU kernels, preserving the checkpoint's tensor contract. It logs per-stage and per-tile timings.

Larger rasters are processed with overlapping 512-pixel tiles. Probability outputs are averaged in overlap regions and padded image edges are cropped back to the source extent. The script preserves source georeferencing in output GeoTIFFs.

## Environment

Use Python 3.10 or later. The minimal dependencies for local inference, evaluation, and tests are listed in `requirements-inference.txt` (TensorFlow, NumPy, Rasterio, and Matplotlib). Geographic pixel areas use Rasterio/GDAL's EPSG:6933 equal-area transform; PyProj is not required. Install in an appropriate environment with:

```bash
python -m pip install -r requirements-inference.txt
```

The verified environment for this Windows run is the repository `.venv` (Python 3.12.10, TensorFlow 2.21.0, Rasterio 1.5.2, NumPy 2.5.4, Matplotlib 3.11.2). TensorFlow is CPU-only on this machine. The original `requirements.txt` remains for the broader notebook and optional acquisition workflows.

## Run inference

From the repository root:

```bash
python scripts/predict_flood.py data/S1GRDHand/India_1017769_S1Hand.tif \
  --model models/best_unet_flood.keras \
  --output-dir outputs/india/predictions
```

Outputs include a probability GeoTIFF, a binary mask GeoTIFF (`255` marks invalid pixels), a JSON/CSV summary, and a PNG with VV, VH, probability, and overlay panels. Geographic-coordinate pixel footprints are transformed into the EPSG:6933 equal-area CRS; projected rasters use affine pixel area and CRS unit conversion. If CRS geometry is unavailable, area is omitted.

To discover compatible India-named scenes automatically (case-insensitive search under `data/S1GRDHand`) and process one scene by default:

```bash
python scripts/predict_flood.py --discover-india --max-images 1 \
  --output-dir outputs/india/predictions
```

Use a positive `--max-images` to set a small batch. `--max-images 0` means every discovered India scene and may take substantial CPU time; it is not the default.

## Local dashboard and uploaded images

Start the preserved globe and API from the repository root in Windows PowerShell:

```powershell
.venv\Scripts\python.exe scripts\run_server.py --host 127.0.0.1 --port 8005
```

Open `http://127.0.0.1:8005/`. The **Satellite Flood Detection & Monitoring** panel accepts a georeferenced two-band Sentinel-1 GeoTIFF (band 1 VV, band 2 VH), up to 100 MiB. It displays the fresh probability/mask overlay, segmented pixel fraction, physical area when CRS is available, and processing timings; outputs are downloadable GeoTIFFs. JPEG/PNG and other inputs are rejected because this checkpoint expects SAR. Each upload writes to a new `outputs/upload_inference_<UTC timestamp>_<hash>/` directory. The dashboard calls `/api/satellite/process` with multipart field `image`.

Native Windows Keras inference was unexpectedly slow on this 32-logical-CPU, CPU-only setup. The CLI and API now convert the unchanged checkpoint once to a float32 TFLite artifact in `outputs/model_cache/` and use XNNPACK. This preserves the model's input/output shapes and numerical output (the measured probability-map maximum difference from the prior Keras output was `3.22e-6`, with no changed mask pixels). The cache filename is checkpoint-SHA keyed; the original `.keras` checkpoint is never modified. Per-stage timings are recorded in each run's summary JSON. Benchmark thread settings with:

```powershell
.venv\Scripts\python.exe scripts\benchmark_cpu_threads.py --model outputs\model_cache\best_unet_flood_6f20437ef60a.tflite
```

For a repeatable fresh source-scene inference in its own timestamped directory:

```powershell
$out = "outputs\fresh_inference_$(Get-Date -Format yyyyMMdd_HHmmss)"
.venv\Scripts\python.exe scripts\predict_flood.py data\S1GRDHand\India_1017769_S1Hand.tif `
  --model models\best_unet_flood.keras --runtime tflite `
  --output-dir $out
```

The current saved scene catalog lacks verified acquisition timestamps and a documented aligned pair, so before/after change detection is unavailable. Future flood-event probability is also unavailable: water segmentation and river discharge are not future event forecasts. The held-out Sen1Floods11 India test summary is in `outputs/india/metrics/summary.json` and reports pooled IoU 0.609 and Dice/F1 0.757 at threshold 0.5 across 14 test scenes.

### Reproduce the India_1017769 demonstration

Fresh CPU inference and exact-scene label comparison are saved in `outputs/fresh_inference_20261110_final/`. The fresh run produced 151,813/262,144 segmented pixels (57.912%) and 13.518 km² on the georeferenced source grid. Its paired `LabelHand` mask is in the **training split**, so exact-scene scores are exploratory and are not held-out validation: IoU 0.7452, Dice/F1 0.8540, precision 0.8011, recall 0.9144, accuracy 0.8226 (172,971 labeled pixels).

A real before/after example is available in `outputs/before_after_India_1017769/`. Recreate the small same-orbit Sentinel-1 RTC crops (requires internet access to the public Planetary Computer catalog and anonymous SAS URL signing), then process both dates and make the change report:

```powershell
.venv\Scripts\python.exe scripts\acquire_india_before_after.py
.venv\Scripts\python.exe scripts\predict_flood.py outputs\before_after_India_1017769\before_2016-07-19_VV_VH.tif --output-dir outputs\before_after_India_1017769\predictions\before --runtime tflite
.venv\Scripts\python.exe scripts\predict_flood.py outputs\before_after_India_1017769\after_2016-08-12_VV_VH.tif --output-dir outputs\before_after_India_1017769\predictions\after --runtime tflite
.venv\Scripts\python.exe scripts\compare_before_after.py
```

The dashboard exposes this saved pair at `/api/before-after/demo`; choose **Load verified India example** in the Before & After section. The acquisitions are 24 days apart and use the same relative orbit and VV/VH polarizations, warped to one grid. Both U-Net masks are empty at threshold 0.50 (0% segmented); that is an exploratory model/domain result, not evidence of no flooding. RTC linear gamma0 is converted to dB before the unchanged model normalization. The report notes calibration/domain differences and does not claim confirmed flood change.

The Alipingal panel reports its archived 2024-05-09 reading as stale (915 approximate calendar days old as of 2026-11-10), includes warning (10.85 m), danger (11.76 m), and historical high (13.11 m), and suppresses current threshold classification until a fresh comparable observation exists. The separate 24-hour forecast remains unavailable.

## Run evaluation

Evaluate the India scenes in the official held-out split against the saved prediction rasters:

```bash
python scripts/evaluate_model.py --split splits/flood_test_data.txt \
  --country India --prediction-dir outputs/india/predictions \
  --threshold 0.5 --output-dir outputs/india/metrics
```

The evaluator verifies label and raster alignment, excludes unknown labels and invalid pixels, and saves per-scene metrics, micro-averaged pixel metrics, macro-averaged scene metrics, per-scene comparison figures, and a metric chart. Do not tune a threshold against test results and call it an independent estimate. Omit `--country India` to evaluate all paired scenes in the selected split.

Regenerate all compatible India predictions (incremental outputs and scene status are saved as the run proceeds):

```bash
python scripts/predict_flood.py --discover-india --max-images 0 \
  --model models/best_unet_flood.keras \
  --output-dir outputs/india/predictions --threshold 0.5
```

`--max-images 0` explicitly requests every discovered scene; discovery defaults to one scene to keep an accidental large run bounded.

## Training and notebook

The existing training log records one epoch only; this checkout does not establish a well-trained or production-ready model. Training was not repeated because CPU-only compute and model quality/validation evidence do not justify unplanned retraining before submission. The main notebook contains 133 cells, several Colab/Drive paths, external Earth Engine operations, and training/download cells. It is preserved unchanged; do not run it top to bottom in a local environment. Use the scripts for local reproducibility.

## Future flood forecasting status

The U-Net segments flood extent in a satellite image; it does not predict a future event. Official Odisha/CWC sources publish Alipingal/Devi warning 10.85 m, danger 11.76 m, and historical HFL 13.11 m; this is a river-gauge threshold, not an urban flood label. The local Alipingal telemetry has extreme values above that HFL, a coordinate mismatch, large gaps, and no timezone declaration, so no threshold model is defensible pending CWC quality confirmation. `Sen1Floods11_Metadata.geojson` contains a single acquisition date per event for 12 benchmark events, including one India event dated 2016-08-12. These snapshot masks cannot establish a 24-hour flood-onset target.

A separate, fail-closed forecasting data pipeline is in `forecasting/`. It requires source-attributed, time-aligned inputs and only creates a negative label when continuous surveillance coverage proves the target period was observed. Header-only templates contain no invented values. Run `python scripts/audit_cwc_telemetry.py` to stream-audit the local CWC file; timestamps are kept as naive wall-clock values because the source declares no timezone. Run `python scripts/evaluate_cwc_level_forecast.py` to reproduce a diagnostic Alipingal 24-hour continuous river-level regression pilot. It is not a flood prediction, loses to persistence, and saves no model. The event-model trainer remains fail-closed unless it has both classes and independent chronological groups. Prediction without a validated event model writes `unavailable` with a null probability. See [forecasting/README.md](forecasting/README.md), the [CWC audit](reports/cwc_dataset_audit.md), and the [threshold research](reports/cwc_threshold_research.md).

No event-occurrence model is fitted in this checkout. The data audit also reviewed Google's 2026 Groundsource event archive (2.6 million news-derived positive event reports, 667.1 MB on Zenodo) and open hydrology/rainfall products. That event archive does not supply no-flood surveillance or matched predictors; it was not downloaded because the large positive-only file would not resolve the training-label gap. ERA5 access requires an accepted CDS request/account, while CHIRPS provides open rainfall data but cannot create missing event/non-event labels. The source-by-source rationale and data needed to train are in [docs/Forecast_Data_Assessment.md](docs/Forecast_Data_Assessment.md).

### Historical flood-event records

The separate DesInventar file is `data/floodevents/DesInventar_Geocoded.csv` (18,235,086 bytes; 122,693 source rows in this checkout). It includes 89 countries, impacts recorded after events, mixed date formats, partial dates, and geocodes ranging from administrative centroids to exact administrative matches. It has no event-description field. The actual geocode bounding rectangle is about 53.10°S–50.89°N and 175.27°W–171.96°E; this does not imply continuous data coverage. The preprocessor uses validated source `GEO_LAT/GEO_LON` fields because original `LAT/LON` contain invalid coordinates, keeps partial dates explicitly, removes only exact duplicate rows, and leaves missing impact fields blank. It writes a cleaned table and 1-degree **reported-record count** bins. The bins and nearby-event API are descriptive historical record density, not exposure-normalized risk, not a supervised model, and not future-event probabilities. There are no non-event surveillance intervals or exposure denominators in this file, so a genuine event-occurrence ML model cannot be trained without additional data.

India-specific coordinate check: 1,059 source rows have `Country=India`. Their raw `LAT/LON` values are present but both equal `0`, a placeholder. `GEO_LAT/GEO_LON` contain valid administrative geocodes produced through fuzzy ADM2 matching; these are not verified event-site coordinates and should not be used to claim precise event-to-river-gauge matches.

Run the reproducible cleaning and hotspot summary:

```bash
python scripts/preprocess_flood_events.py
```

Outputs are `outputs/flood_events/desinventar_cleaned.csv`, `preprocessing_report.json`, and `historical_1deg_record_counts.csv`. The API's `/api/query?lat=...&lon=...` response includes `historical_event_reports` with nearby reports (default 25 km, configurable from 1–100 km using `event_radius_km`). Records include date precision and the source geocoding method; a point is not a flood boundary. No event impact variables are used as predictors.

Official services describe data that may support a future model: IMD documents AWS observation and forecast products; CWC publishes station and basin forecasts; Tamil Nadu's Chennai Flood Monitoring system describes 72-hour basin forecasts. The local CWC Mahanadi file is an observation archive, not an operational forecast. Alipingal has official published thresholds, but telemetry quality/station identity has not been reconciled. The IMD API requests checked during prior work returned HTTP 401. Acquire missing data through an authorized route and document it before training. External operational forecasts are not generated by this repository.

## Local GloFAS GRIB data

Both files under `data/glofas/` were inspected read-only with Rasterio/GDAL's GRIB2 driver. `data.grib` contains 60 ECMWF control-forecast records of hydrological parameter `discipline=1/category=0/number=7` (river/stream discharge, m³/s), with 20 initialization dates from 2025-01-01 through 2025-01-20 and valid interval ends through 2025-01-23 (24/48/72-hour leads per cycle). `data1.grib` contains two ECMWF analysis-type records with reference time 2016-08-12 and a valid interval end 2016-08-13; its local product template differs and its field details are not fully named by GDAL. Both files use the same 7200×3000 EPSG:4326 grid at 0.05° spacing, bounds longitude −180° to 180° and latitude −60° to 90°. Each field has 6,221,926 valid river-grid cells and 15,378,074 masked cells; nodata is 9999. The GRIB local product templates are 73 and 72 respectively, with ECMWF master tables 32 and 36. An explicit GloFAS release identifier is not present in the exposed metadata, so the inventory records the files as ECMWF hydrological discharge data consistent with GloFAS, not as a confirmed release/version.

The files share parameter and grid but have different product templates, analysis/forecast types, and non-overlapping times, so they are not concatenated as one series. The 2025 forecast file is stale for current operational use. `scripts/inspect_glofas.py` writes full record and bitmap metadata to `outputs/forecasting/glofas_inventory.json`. `scripts/export_glofas_point.py` performs bounded nearest-river-cell queries and exports issue/valid times, lead, source-cell distance, and discharge value; it does not infer flood probability. GloFAS documentation advises checking a grid cell's upstream area and cautions about smaller catchments. No upstream-area layer is present here, so nearest-cell results are exploratory and their relevance to a local scene is unverified. Example using an existing georeferenced scene:

```bash
python scripts/inspect_glofas.py
python scripts/export_glofas_point.py --scene data/S1GRDHand/India_25540_S1Hand.tif
```

The example output is `outputs/forecasting/glofas_point_forecast.csv` and companion JSON. GloFAS documentation describes daily mean river discharge as m³/s; these values remain hydrological forecasts, not local flood occurrence or urban inundation predictions. The native local product template fields have not been fully decoded because ecCodes definitions could not be installed offline. Copernicus EMS GloFAS data are provided under service terms; any further distribution must follow those terms, including source attribution and modified-data notice where applicable. They explicitly state the information is not an official flood warning. For redistributed results, apply the current [CEMS-FLOODS terms](https://cds.climate.copernicus.eu/licences/cems-floods), which specify source notices such as “Generated using Copernicus Emergency Management Service information [Year]” and, for modified data, “Contains modified Copernicus Emergency Management Service information [Year]”. See also the [GloFAS model output notes](https://confluence.ecmwf.int/pages/viewpage.action?navigatingVersions=true&pageId=400501522).

The 60 × 3,000 × 7,200 global float64 cube would require about 10.4 GB before masks, decoder buffers, or temporary copies. Do not materialize it with xarray/cfgrib on the available 7.6 GiB machine. The precise earlier termination stage was not reproduced. Use the Rasterio/GDAL path above, which reads a bounded nearest-cell window and one pixel per record, and preserve the `.idx` sidecar. See [memory-safe access notes](forecasting/README.md#memory-safe-access).

When preparing eventual event-model features, pass this export as `--glofas-export outputs/forecasting/glofas_point_forecast.csv` to `scripts/prepare_forecast_dataset.py`. The join requires matching `location_id`, an issue time no later than the sample issue, and a 24-hour valid interval covering the target period; nonmatching rows remain unlabeled/invalid.

## Global coordinate service and local interface

From the repository root run:

```bash
python scripts/preprocess_flood_events.py
python scripts/run_server.py --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/`. Port 8000 may be occupied by an older project server; verify the active service at `/api/health`, which should report `api_version: india-location-demo-4`. The offline UI opens centered on India and draws a rotatable, zoomable Earth with Natural Earth 1:110m country polygons, coastlines, borders, graticules, and ocean/sea labels. Drag to rotate and scroll or use +/- to zoom. The location selector lists Indian city/state reference points that currently have a river-network cell within 30 km in the local GloFAS grid; selecting one fills coordinates and calls `/api/query`. These 15 locations span 14 states plus Delhi NCT. The Chennai shortcut remains available, as do globe clicks and manual coordinates. The local texture works without a third-party map service or API key. Markers distinguish saved satellite scene centers, nearby historical event geocodes, and the nearest river cell; a future-risk marker is not shown while no event model is available. The UI reports stale forecast dates, specific forecast-data limitations, and unsupported locations. The Alipingal historical threshold-demo action uses `/api/demo-prediction?station=alipingal-devi`; it classifies the latest screened archived gauge reading and does not forecast the next 24 hours. The separate **24-Hour Prediction Demo** uses `/api/river-level-prediction?station=alipingal-devi` and displays the stale observation, rejected Ridge/persistence test metrics, and an explicit unavailable prediction. Endpoints include `/api/health`, `/api/availability`, `/api/india-locations`, `/api/detections?bbox=west,south,east,north`, `/api/detections?since=YYYY-MM-DD&until=YYYY-MM-DD`, and `/api/query?lat=13.0827&lon=80.2707&horizon_hours=24` (the horizon may be 24, 48, or 72; optional `event_radius_km` defaults to 25). The local prediction catalog currently contains 68 India benchmark scenes; worldwide coordinate queries return only sources with actual local coverage. The city/state list checks actual river-cell coverage, but proximity does not establish hydrological representativeness; the available GloFAS records are stale through 2025-01-23.

The globe data are Natural Earth 1:110m admin-0 country geometries (177 features; public domain). `frontend/earth_countries.geojson` is bundled locally and `frontend/assets/earth_texture.png` is its generated equirectangular rendering. Regenerate the texture with `python scripts/build_earth_texture.py` (requires Pillow). See [frontend/EARTH_DATA.md](frontend/EARTH_DATA.md) for provenance and source checksum.

The backend keeps historical event reports, current satellite segmentation, and future event prediction separate: `future_flood_event_prediction.status` is `unavailable` with `probability: null`. GloFAS forecasts are returned in their own object as stale river-discharge records, not as risk categories. There is no authentication; bind only to localhost unless the deployment is secured separately.

## Current evidence and limitations

- Model load and architecture were verified locally.
- Automatic discovery found 68 compatible India SAR scenes. 67 were newly processed, one valid cached scene was reused, and zero were skipped. Per-scene summaries, masks, probability rasters, visualizations, and a consolidated prediction CSV are under `outputs/india/predictions/`.
- All 14 India scenes in the official held-out test split were evaluated against aligned hand labels at threshold 0.5 (zero skipped). Pooled pixel metrics: precision 0.8903, recall 0.6584, Dice 0.7570, IoU 0.6090, accuracy 0.9100, specificity 0.9781; TP=451,970, TN=2,481,987, FP=55,674, FN=234,537. Macro scene means: precision 0.6554, recall 0.2832, Dice 0.3045, IoU 0.2578, accuracy 0.9152, specificity 0.9514. This is a benchmark subset, not nationwide validation.
- Per-scene metrics are in `outputs/india/metrics/per_image_metrics.csv`; ground-truth comparison panels are in `outputs/india/metrics/evaluation_figures/`; aggregate summary and the F1/IoU chart are in `outputs/india/metrics/`.
- Existing `outputs/test_results.json` reports precision 0.8612, recall 0.6082, Dice 0.7129, IoU 0.5539, accuracy 0.9387, and specificity 0.9860. These are prior stored values and are not treated as reproduced metrics.
- The one-epoch training log has validation Dice 0.3474 and validation IoU 0.2932. The checkpoint's broader training history is unavailable; the difference between macro and micro test metrics also shows uneven scene-level performance.
- No scene dates or geographically representative nationwide India validation are established by the current outputs. Predictions must be interpreted with that limitation.

## Tests

Run the lightweight unit tests from the repository root:

```bash
python -m unittest discover -s tests -v
```

They cover normalization, tile edge coverage and blending, invalid overlap settings, projected/geographic area calculations, metric edge cases, and India scene discovery. Model loading and real inference were additionally exercised on the saved checkpoint and `India_900498` scene during this handoff.

## Repository guide

- `scripts/predict_flood.py` — reusable tiled inference and outputs
- `scripts/preprocess_flood_events.py` — DesInventar cleaning and descriptive record-count bins
- `scripts/build_earth_texture.py` — reproducibly rasterize the bundled Natural Earth GeoJSON
- `scripts/inspect_glofas.py` — GRIB2 field, grid, time, and bitmap inventory
- `scripts/export_glofas_point.py` — nearest supported river-cell time series
- `scripts/run_server.py` — local API and static interface
- `src/flood_app/server.py` — global coordinate API and availability status
- `forecasting/desinventar.py` — CSV normalization and nearby historical-event index
- `frontend/index.html` — offline interactive globe and local data UI
- `frontend/earth_countries.geojson`, `frontend/assets/earth_texture.png` — bundled public-domain basemap source and generated texture
- `frontend/EARTH_DATA.md` — map source license and checksum
- `scripts/evaluate_model.py` — paired-mask metrics on official splits
- `scripts/prepare_forecast_dataset.py` — strict source/time-aware future-onset labels
- `scripts/train_forecaster.py` — gated experimental 24-hour tabular baseline
- `scripts/predict_future_flood.py` — fail-closed future forecast interface
- `forecasting/` — forecasting schemas and limitations
- `notebook/` — original exploratory Colab notebook, retained
- `models/` — current checkpoint and preserved backup
- `outputs/` — historical artifacts and reproducible India results
- `docs/` — methodology notes
- `report/Technical_Report.md` — concise academic technical report
- `report/Project_Report.pdf` — preserved original PDF; use the current Markdown report and output metrics for this run's verified results

## Reference

Bonafilia, D., Tellman, B., Anderson, T., & Issenberg, E. (2020). *Sen1Floods11: A georeferenced dataset to train and test deep learning flood algorithms for Sentinel-1*. IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshops.
