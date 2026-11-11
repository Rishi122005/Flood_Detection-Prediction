# Completion checklist: global flood project

## Current verification addendum (2026-11-11)

The current Windows checkout has no usable Git metadata (`.git` is absent), so current changes cannot be summarized with `git diff/status`. The saved U-Net checkpoint remains untouched. The API has been advanced to `india-location-demo-6`.

Verification completed on this checkout: `.venv\Scripts\python.exe -m unittest discover -s tests -v` passed **53/53** tests. `node scripts\verify_dashboard_browser.cjs` passed against the updated backend on port 8005, including actual browser rendering, cluster hover/click, location and scene selection, stale-data states, before/after comparison, three live Open-Meteo locations, manual weather coordinates and a fresh satellite upload. Fresh satellite outputs are in `outputs/upload_inference_20261110_183552_331176_3db2f06ab052/`: `upload_3db2f06ab052_mask.tif`, `upload_3db2f06ab052_probability.tif`, `upload_3db2f06ab052_prediction.png`, and the summary JSON. Earlier checklist entries below describe prior checkpoints and their historical test counts; this addendum is current.

| Area | Current verified status | Limitation |
|---|---|---|
| Globe detections | `/api/detections` exposes source, valid, invalid and displayed counts. Current catalog has 68/68 valid WGS84 scene centers. Frontend groups overlapping visible centers into numbered clusters, supports cluster hover/click, and retains individual scene selection. | Markers denote scene footprint centers/model outputs, not confirmed event coordinates. Acquisition timestamps are absent from these summary records. |
| External discharge | Stale GloFAS records are separated as archived and cannot populate current forecast fields. The UI uses the required unavailable message when no valid future forecast exists. | Local forecast archive is from Jan 2025 and is stale as of this verification; nearest river cell does not prove local representativeness. |
| Gauge demo | Displays station, observed value/time/age, warning/danger thresholds and historical HFL; stale classification is not presented as current or forecast. | Latest bundled Alipingal reading is 4.001 m at 2024-05-09 04:00, stale; timezone metadata is unspecified. |
| Before/after | Existing co-registered Sentinel-1 orbit-77 VV/VH scenes (2016-07-19 and 2016-08-12) and model masks are shown with scene IDs, timestamps and change counts. | Both masks are empty at the configured threshold; this does not establish flood-free conditions. Exploratory only. |
| Future flood prediction | Explicitly unavailable; no model forecast or probability is emitted. | CWC observations have major gaps, stale coverage, unresolved station/quality issues and no reliable threshold-event labels; local GloFAS is not issue-time aligned. |
| Satellite processing | Fresh upload uses the saved U-Net, real two-band VV/VH GeoTIFF, tiled inference, downloadable mask/probability/overlay and area where georeferencing supports it. | Segmentation is not independent flood confirmation. PNG/JPEG are incompatible with this checkpoint. |
| Weather-based screening | API v6 adds independent `/api/weather-risk` and `/api/weather-risk/locations` routes using live Open-Meteo values. Browser verification fetched Guwahati, Chennai, and Patna forecasts and rendered 24 hourly bars per location; manual Bengaluru coordinates and invalid latitude validation also ran. | Rule-based rainfall screening only; no river/terrain/soil/drainage representation, official thresholds, flood probability, or validated future flood model. API retrieval time is provided; upstream model issue time is not. |

Demonstration: use the weather-enabled server on `http://127.0.0.1:8005/`; choose Guwahati, Chennai, and Patna in the weather module and confirm each chart/data update; select manual coordinates and try an invalid latitude; check the globe markers and scene ID; inspect stale discharge/gauge labels; load before/after analysis; upload `data/S1GRDHand/India_1017769_S1Hand.tif` for fresh segmentation outputs. Start a new backend with `.venv\Scripts\python.exe scripts\run_server.py --host 127.0.0.1 --port 8005`. Browser check: `$env:FLOOD_TEST_PORT='8005'; node scripts\verify_dashboard_browser.cjs`. Run tests with `.venv\Scripts\python.exe -m unittest discover -s tests -v`.

| Requirement | Status and evidence | Remaining limitation |
|---|---|---|
| Preserve original work/checkpoints | Complete for this run. Pre/post SHA-256 of both U-Net artifacts: `6f20437ef60a01d03c8f2b3ba93bbd04188278ae7906ca99b99618be48922720`. Existing inference outputs and notebook retained. | `.git` is an empty directory, not a usable Git worktree; no diff/status available. |
| Baseline tests before edits | Complete: `python -m unittest discover -s tests -v`, 14/14 passed before this run's changes. | None. |
| Inspect supplied GloFAS GRIB2 | Implemented `scripts/inspect_glofas.py`; run against both files; inventory at `outputs/forecasting/glofas_inventory.json`. 60 forecast records + 2 analysis records, common grid/mask, 0 duplicates within files. | ecCodes definitions were unavailable offline, leaving ECMWF local PDT 72/73 field semantics and explicit release version unknown. |
| GloFAS coordinate/time handling | Complete: `python scripts/export_glofas_point.py --scene data/S1GRDHand/India_25540_S1Hand.tif` exported 60 records, valid issue/valid times and 24/48/72-hour leads; nearest cell is 2.137 km. As-of alignment is unit-tested in `forecasting/pipeline.py`. | Local forecast valid through 2025-01-23 is stale. No live feed/API credentials. |
| Satellite detection | Existing U-Net prediction/evaluation scripts reused; 68 local saved georeferenced scene outputs are catalogued and pixel-queryable by the API. Existing 14-scene India evaluation remains preserved. | Local saved predictions are India-only; acquisition dates are not carried in prediction provenance. |
| Future flood-event model | Re-ran preparation (0 labeled rows) and the trainer (refused at 0 independent groups); API returns `not_trained`, null probability, an unselected horizon, and specific missing-input requirements. | No verified non-event surveillance or matched pre-event weather/gauge time series; no event model or metrics can honestly be reported. |
| Historical DesInventar records | Preprocessed the actual 122,693-row source across 89 countries; all records have valid supplied `GEO_LAT/GEO_LON`; wrote cleaned CSV, audit report, 1-degree record-count bins, and explicit `not_trained` model status. Integrated nearby reports into `/api/query` and globe UI. | Presence-only reports, post-event impacts, and administrative/fuzzy geocodes do not support future event prediction or exposure-normalized risk. |
| External forecasting data review | Complete: assessed Groundsource (667.1 MB event-only archive), Google GRRR and API, ERA5, and CHIRPS; see `docs/Forecast_Data_Assessment.md`. | Groundsource provides positive event reports without verified negatives or weather features; not downloaded because it is large and cannot solve the label gap. ERA5 requires CDS account/terms; no credentials. CHIRPS precipitation alone cannot supply flood outcomes. |
| Real geographical globe | Bundled 177-feature Natural Earth 1:110m GeoJSON and generated 1440×720 offline texture. Dark dashboard projects real coastlines/borders onto an orthographic globe, defaults to India, supports rotate/click/12× zoom, and has a Chennai quick-select that centers the map and submits its reference coordinates. HTTP serves UI and texture successfully. | No browser/JavaScript engine is installed, so actual button/canvas interaction needs manual browser verification. |
| Global geographic support | Coordinate query, bounding-box filtering, local footprint catalog, and nearest river-grid cell lookup implemented. Unsupported coordinates return explicit status. | Data support is limited to river-mask cells in the local GloFAS raster and 68 India satellite footprints. No global place-name gazetteer. |
| Backend and interface | Standard-library API and existing dark dashboard use a bundled offline Natural Earth globe texture with coastlines/country borders, rotation, zoom controls, location selection, and satellite/historical/river markers. Headless Chrome now verifies rendering and API-populated location choices. | No global place-name gazetteer. |
| Dependencies | Existing Python packages are sufficient; Pillow was already installed. No package upgrades performed. | Training libraries are absent, but data do not meet the event-model training criteria. |
| Final tests | Current run: `python -m unittest discover -s tests -v`: 25/25 passed; Python compile and HTML parse passed; preprocessing ran against source CSV; localhost HTTP returned 200 for UI, Earth texture, availability, and nearby event query; both checkpoints match original hashes. | Browser JavaScript/rendering and manual Chennai coordinate selection remain unverified in this environment. |

## Commands executed in this run

- `python scripts/preprocess_flood_events.py`: processed 122,693 source rows; 122,693 geocodes passed validation; 89 countries and 2,214 occupied one-degree bins; model status remains `not_trained`.
- `python scripts/prepare_forecast_dataset.py --features forecasting/templates/features.csv --events forecasting/templates/events.csv --coverage forecasting/templates/coverage.csv --glofas-export outputs/forecasting/glofas_point_forecast.csv`: 0 labeled rows, report `no_labeled_samples`.
- `python scripts/train_forecaster.py`: exit 2 with gate `need at least 10 independent evaluation groups; found 0`; no model artifact or metrics generated.
- Researched Groundsource, Google GRRR/API, ERA5, and CHIRPS; assessment at `docs/Forecast_Data_Assessment.md`. Did not fetch 667.1 MB positive-only Groundsource archive because it does not provide negative surveillance or predictor series.
- Downloaded and bundled 838,726 bytes of Natural Earth 1:110m Admin 0 country polygons; provenance, public-domain terms, and SHA-256 are in `frontend/EARTH_DATA.md`.
- `python scripts/build_earth_texture.py`: generated the 1440×720 `frontend/assets/earth_texture.png`, which was visually inspected.
- `python -m unittest discover -s tests -v`: 25/25 passed.
- `python -m py_compile scripts/build_earth_texture.py forecasting/desinventar.py src/flood_app/server.py tests/test_earth_globe.py tests/test_global_service.py`: passed. Python HTML parser accepted the dashboard markup. No JavaScript/browser runtime is installed.
- Temporary localhost HTTP integration: `/` and `/api/health`, `/api/availability`, and a real coordinate query returned HTTP 200; `/assets/earth_texture.png` returned `image/png`; query returned nearby historical rows while future-event probability remained null.
- Actual server entry point queried Chennai (`13.0827,80.2707`): HTTP 200; future flood result was explicitly unavailable with null probability and four missing-data requirements.
- `python scripts/inspect_glofas.py` and `python scripts/export_glofas_point.py --scene data/S1GRDHand/India_25540_S1Hand.tif`: the two real GRIBs were inventoried and 60 point records exported; see `outputs/forecasting/`.
- `python scripts/prepare_forecast_dataset.py ...`: generated zero labeled samples from empty time-series/event/coverage templates. `python scripts/train_forecaster.py` refused training at 0 independent groups; missing-model prediction returned unavailable/null.
- `sha256sum models/best_unet_flood.keras models/best_unet_flood_backup.keras`: both match `6f20437ef60a01d03c8f2b3ba93bbd04188278ae7906ca99b99618be48922720`; original model architecture/load was previously verified.

## Follow-up: memory-safe GloFAS and future-forecast readiness

| Check | Result | Evidence / limitation |
|---|---|---|
| GRIB memory sizing | Complete | `data.grib` has 60 global 3,000×7,200 float64 records. A dense cube requires about 10.4 GB before masks or decoder/copy overhead, above the machine's 7.6 GiB RAM; swap was full during this check. The exact earlier process-kill stage was not reproduced. |
| Bounded GRIB data reads | Complete | Existing Rasterio/GDAL point-query implementation reads a local nearest-river search window and 1×1 values per forecast band; a regression test now rejects unwindowed reads. The existing point export contains 60 records. A fresh CLI extraction attempt did not complete within the 30-second execution window, so it is not reported as passed in this follow-up. |
| India event coordinates | Verified | Streaming scan of `DesInventar_Geocoded.csv`: 1,059 India rows; all raw `LAT/LON` are 0,0. `GEO_LAT/GEO_LON` are valid but use fuzzy ADM2 administrative geocoding, not verified event locations. They are not suitable for defensible event-to-river matching. |
| Forecast training gate | Verified fail-closed | `python scripts/train_forecaster.py` exited 2 because there are 0 independent labeled evaluation groups; no model was created. Required issue-time predictors, event-onset labels, and documented non-event coverage are absent. |
| Regression and repository tests | Complete | `python -m unittest discover -s tests -v`: 26/26 passed after adding `test_forecast_extraction_only_reads_bounded_windows`. |
| Existing UI and GLB | Preserved | No `.glb`/`.gltf` file exists under `frontend/`; the existing offline canvas globe and local geography assets remain in place. No frontend changes were made. |

This follow-up changed only `README.md`, `forecasting/README.md`, `docs/Completion_Checklist.md`, and `tests/test_forecast_pipeline.py`. Original datasets and U-Net checkpoints were not modified. The point-export CSV is an external hydrological forecast product, not a future flood-event probability.

## Presentation demo: Indian location-based river discharge

| Check | Result | Evidence / limitation |
|---|---|---|
| Indian city/state selector | Complete | Added `/api/india-locations` and a UI selector populated only by locations with a valid river-grid cell within 30 km. The current GRIB supports Delhi, Mumbai, Kolkata, Chennai, Bengaluru, Hyderabad, Ahmedabad, Jaipur, Lucknow, Patna, Guwahati, Vijayawada, Srinagar, Dehradun, and Bhubaneswar (14 states plus Delhi NCT). |
| UI-to-API integration | Complete | Selecting a location fills coordinates and requests `/api/query`; the existing rotatable Earth globe remains unchanged and centers/marks the selection. The page is served with the selector and the local Earth texture. |
| Real discharge response | Verified | Local endpoint smoke test for Chennai returned 3.125 m³/s for the 24-hour lead, issued 2025-01-20, valid 2025-01-20 through 2025-01-21. The response marks discharge stale and future flood-event probability unavailable/null. |
| Application process | Running | Updated application is serving on `http://127.0.0.1:8001/`. Port 8000 was already occupied by an older project-server process, which was left untouched. |
| Tests | Complete | `python -m unittest discover -s tests -v`: 28/28 passed. `py_compile` passed. Local HTTP health, location list, Chennai query, UI page, and globe texture returned successful responses. |
| Scope and limitation | Explicit | The 15 locations are presentation presets with nearby river-grid support, not proof that a river cell represents urban inundation. The only available records are stale through 2025-01-23. No event-occurrence model or flood probability is available. |

Files changed for this demo: `src/flood_app/india_locations.py`, `src/flood_app/server.py`, `frontend/index.html`, `tests/test_global_service.py`, `tests/test_earth_globe.py`, and `README.md`. No GLB/GLTF file was found in the repository; the existing offline globe and texture are served and preserved.

## Dashboard loading diagnosis and recovery

| Check | Result | Evidence |
|---|---|---|
| Port identity | Confirmed stale-server collision | Port 8000 responds with the old health schema and returns 404 for `/api/india-locations`. Port 8001 responds with `api_version: india-location-demo-1` and serves the new location endpoint. The existing 8000 process was left untouched. |
| Dashboard resources | Pass | On port 8001, `/`, `/assets/earth_texture.png`, `/api/availability`, `/api/detections`, `/api/india-locations`, and `/api/health` return HTTP 200. The HTML is 30,720 bytes, texture is 262,073 bytes, and 15 locations are returned. |
| Cache/API diagnostics | Implemented | Static assets and JSON responses now send `Cache-Control: no-store`; `/api/health` and `X-Flood-App-Version` identify the updated server. The UI checks the expected API version, uses 10-second request timeouts, and displays API/init errors instead of leaving loading text indefinitely. |
| Globe and browser verification | Pass | Windows Chrome headless loaded the page, executed its scripts, fetched all APIs and the local texture, rendered the 560×560 canvas globe, populated all 15 supported locations, and updated service/footer status. Screenshot was visually inspected. |
| Regression checks | Pass | `python -m unittest discover -s tests -v`: 28/28 passed; Python compilation passed. Local HTTP smoke checks verified the service endpoints. |

Recovery command: `python scripts/run_server.py --host 127.0.0.1 --port 8001`. Open `http://127.0.0.1:8001/` and hard-refresh once. `/api/health` must show `india-location-demo-1`; the old server on port 8000 is not the updated demo backend. Headless Chrome DOM inspection confirmed the service status updated, the coverage footer populated, and the selector contained the placeholder plus all 15 supported options.

## CWC Mahanadi telemetry audit and forecast readiness

| Requirement | Status | Evidence |
|---|---|---|
| Locate and inspect the specified CSV | Complete | `data/observations/cwc_mahanadi_telemetry_2021_2025.csv`, 148,640,758 bytes; 921,203 rows and 37 station keys. Schema and timestamp format are recorded in `reports/cwc_dataset_audit.md` and `.json`. |
| Memory-efficient reusable audit | Complete | `python scripts/audit_cwc_telemetry.py` streams the CSV and uses a temporary on-disk SQLite index when records are not ordered by station/time. |
| Station coverage and data quality | Complete with correction | Valid period 2021-01-01 to 2025-12-30; 163 duplicate timestamps, 53,848 gaps over one hour; timezone unspecified, timestamps are naive wall-clock values (not UTC). |
| Select station and verify threshold | Threshold verified; data blocker remains | Alipingal/Devi official warning 10.85 m, danger 11.76 m, HFL 13.11 m. Telemetry has values above HFL, coordinate mismatch, sparse coverage, and unresolved datum/timezone. RAJIM remains coverage leader but no station threshold was found. See `reports/cwc_threshold_research.md`. |
| Continuous river-level model | Diagnostic only, rejected | A leakage-safe 24-hour pilot ran: 151/28/28 train/validation/test windows; 28 test targets in 4.001–4.002 m range. Ridge MAE/RMSE 0.000366459/0.000422889 m; persistence 0.000142857/0.000377964 m. Ridge loses to persistence. No artifact saved; not a flood prediction. |
| Interactive prediction demonstration | Historical observation; current category unavailable while stale | `/api/demo-prediction?station=alipingal-devi` reports the actual screened observation, timestamp, approximate age, freshness, warning/danger/HFL, and suppresses the category/rule when stale. The 2024 record is historical; there is no probability or future forecast claim. API version is `india-location-demo-4`. |
| Request latency fix | Implemented | `outputs/forecasting/alipingal_demo_cache.json` is built by `scripts/build_cwc_demo_cache.py`, with source size/mtime validation. API requests read the small cache instead of scanning the 149 MB CSV synchronously; stale/missing cache returns a clear unavailable response. |
| 24-hour level prediction panel | Implemented; future output unavailable | `/api/river-level-prediction?station=alipingal-devi` reports the stale latest observation and chronological Ridge-versus-persistence metrics; predicted value remains null because the diagnostic Ridge lost to persistence and did not generalize beyond a narrow low-stage test. |
| Train a flood-event model | Correctly unavailable | No usable threshold-positive examples and no independent event/non-event periods; raw excursions require CWC QC. No flood model artifact or flood metrics were generated; API probability remains null. |
| Backend/dashboard regression | Verified | Server on `127.0.0.1:8001`; `/`, `/api/health`, `/api/availability`, `/api/india-locations`, and a real `/api/query` returned HTTP 200. Query reports event prediction unavailable with null probability. |
| Tests | Complete | Final demo run: `python -m py_compile src/flood_app/server.py scripts/build_cwc_demo_cache.py` and full `python -m unittest discover -s tests` (37 tests), including endpoint dispatch, supported/unsupported station, response fields and frontend panel markup. |

Next required evidence: CWC confirmation of Alipingal station identity, coordinates, vertical datum, timezone, and QC/corrections for readings above HFL, followed by longer verified gauge records with independent high-water and non-event periods. No urban flood inference should be made from a river-stage target.
