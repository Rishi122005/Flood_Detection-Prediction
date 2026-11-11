# Free-tier deployment

## Current state

Deployment files are prepared, but the public services are **not yet created or live**. The Vercel and Northflank accounts must be authorized before service creation. Do not publish a frontend-only deployment as if the full application were running.

| Component | Planned service | Status |
| --- | --- | --- |
| Static dashboard | Vercel Hobby | Configuration ready; account authorization required |
| Python API and U-Net inference | Northflank Sandbox Docker service | Configuration ready; Docker build and account authorization still required |
| API URL / CORS origins | Public Vercel and Northflank domains | Configure after service URLs are assigned |

Add the real HTTPS URLs to this document and the README only after health and inference checks pass.

## Why Northflank

The current Northflank pricing page lists a free Sandbox with up to $20/month in Northflank Cloud resources, no card required, and no service sleep. Its `nf-compute-50` plan provides 0.5 vCPU and 1 GiB RAM and is listed at about $12/month, within that free resource allowance. Free Sandbox compute limits are account controlled. Check that the plan is selectable in the account before creating the service. [Northflank pricing and Sandbox](https://northflank.com/pricing)

Northflank's documented default ephemeral storage limit is 2 GiB. Uploaded inference outputs are directed to `/app/persistent_uploads`; attach a persistent volume at that path so generated masks, probability rasters, overlays, and summaries survive container replacement. Storage and network transfer count toward the monthly resource allowance; keep the projected total under $20/month and do not add a payment method. [Northflank resource plans and quotas](https://northflank.com/docs/v1/application/billing/resource-plans-and-quotas.md)

This is a low-traffic demonstration configuration: CPU is limited to half a core, uploads are serialized around one cached interpreter, and free compute quotas can change. Full-scene inference can be slow. The backend continues to enforce its 100 MiB file limit and four-million-pixel limit.

The DesInventar event catalogue is indexed in a temporary disk-backed SQLite database so startup does not retain 122,693 Python row dictionaries in RAM. On this Windows development machine, full service startup fell from about 460 MiB RSS to 68 MiB. A fresh upload through the full service completed in 28.7 seconds (21.2 seconds inference), with a measured peak working set of 972 MiB. That is close to the 1 GiB limit; the single-process upload lock prevents concurrent model allocations, but the Northflank deployment must still pass its health check and live inference before it can be called supported. The 0.5 vCPU instance may take longer than the local machine.

## Model and dataset packaging

The backend uses LiteRT 2.3.0 to execute the existing float32 TensorFlow Lite conversion from the original Keras U-Net. The conversion uses the same VV/VH input, normalization, 512×512 input tile, sigmoid score output, and 0.5 segmentation threshold. Local comparison against the Keras path found maximum probability difference `3.22e-6` and zero changed mask pixels at the threshold. The conversion and source checkpoint hashes are in [`models/best_unet_flood.tflite.json`](../models/best_unet_flood.tflite.json). The original `models/best_unet_flood.keras` remains unchanged in Git LFS.

The Docker build sparse-checks out only these runtime assets from the public GitHub repository:

- The converted U-Net model.
- Local GloFAS `data.grib` and its index sidecar.
- The saved India prediction catalog and its probability/mask rasters.
- The aligned before/after example outputs.
- The cleaned historical event catalog and compact CWC demo cache.

The full Sentinel-1 training corpus and 148 MB raw CWC CSV are not bundled. Users upload their own compatible VV/VH GeoTIFF; the repository sample `data/S1GRDHand/India_1017769_S1Hand.tif` is suitable for the faculty demo. The compact gauge cache is generated from real CWC telemetry and reports its actual stale observation timestamp. Original project datasets remain available from Git LFS.

Prediction-preview PNGs are converted to WebP inside the container image when smaller. The repository PNG files remain unchanged. User-upload outputs are written under the persistent upload mount. Without the mounted volume they are temporary and may disappear on service replacement.

## Vercel settings

Vercel project root: repository root. `vercel.json` runs `python scripts/build_vercel_frontend.py` and publishes `dist/`. The build requires one public, non-secret environment variable:

| Variable | Example | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `https://<backend-service-domain>` | Dashboard API origin injected during the static build |

The dashboard applies this origin only to `/api/` and backend artifact URLs. Static globe assets stay on Vercel. Uploads go directly from the browser to Northflank; they do not pass through Vercel Functions.

## Northflank service settings

Create a Docker service from the repository's `main` branch, use the root [`Dockerfile`](../Dockerfile), select `nf-compute-50` (0.5 vCPU / 1 GiB), and expose HTTP port `8080` publicly. Configure the platform health check as `GET /api/health`. The Docker image also contains a health check.

Attach a persistent volume mounted at `/app/persistent_uploads`. Keep it within the free Sandbox resource allowance. Configure these environment variables:

| Variable | Value |
| --- | --- |
| `PORT` | Supplied by the platform; the container defaults to `8080` |
| `CORS_ALLOWED_ORIGINS` | Comma-separated exact Vercel HTTPS origins, including preview origin only if needed |
| `FLOOD_UPLOAD_OUTPUT_DIR` | `/app/persistent_uploads` |
| `FLOOD_TFLITE_RUNTIME_ONLY` | `1` |
| `FLOOD_TFLITE_THREADS` | `1` |
| `FLOOD_ALLOW_PREBUILT_CWC_CACHE` | `1` |

No API keys are required for the current Open-Meteo integration. Do not add credentials to frontend settings.

## Deployment and verification sequence

1. Authenticate to Northflank and create the free Sandbox service with the settings above. Wait for the Docker build and health check to pass, then copy its HTTPS domain.
2. Set Northflank `CORS_ALLOWED_ORIGINS` to the Vercel domain that will be used.
3. Authenticate to Vercel, link the repository, set `API_BASE_URL` to the Northflank HTTPS origin, and deploy the static site.
4. Add the resulting exact Vercel origin to Northflank `CORS_ALLOWED_ORIGINS`; redeploy/restart the backend if required.
5. Verify Vercel `/`, backend `/api/health`, `/api/availability`, `/api/detections`, `/api/before-after/demo`, and `/api/weather-risk?city=delhi` from the browser.
6. Upload `data/S1GRDHand/India_1017769_S1Hand.tif` through **Satellite Flood Detection & Monitoring**. Verify a new run ID, fresh mask, probability raster, overlay, pixel percentage, and area; download all three output artifacts.
7. Select a saved scene, view the before/after panel and globe, and confirm that stale GloFAS/CWC information is labelled as historical/unavailable where appropriate.
8. Recheck the monthly Northflank resource estimate and persistent-volume setting. Do not exceed the free allowance.

## Known limitations

- Northflank's free resource allowance and eligible compute plans are account/region dependent and may change. Verify the `nf-compute-50` option before provisioning.
- The service has no GPU and only 0.5 vCPU; uploaded inference will be slower than on the development machine.
- The default 2 GiB ephemeral storage is not persistent. A persistent upload volume is required for saved output links to survive restarts.
- The raw CWC CSV is omitted; only the compact verified gauge cache is used for the threshold demo.
- Local GloFAS files are historical/stale and are not an operational current forecast.
- A frontend URL is not proof of a working deployment. Deployment remains incomplete until the backend and a real remote inference have passed the checks above.
