FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    FLOOD_TFLITE_RUNTIME_ONLY=1 \
    FLOOD_TFLITE_THREADS=1 \
    FLOOD_ALLOW_PREBUILT_CWC_CACHE=1 \
    FLOOD_UPLOAD_OUTPUT_DIR=/app/persistent_uploads \
    TF_NUM_INTRAOP_THREADS=1 \
    TF_NUM_INTEROP_THREADS=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git git-lfs \
    && rm -rf /var/lib/apt/lists/* \
    && python -m pip install --no-cache-dir --upgrade pip

COPY requirements-cloud.txt ./requirements-cloud.txt
RUN python -m pip install --no-cache-dir -r requirements-cloud.txt

COPY src ./src
COPY scripts ./scripts
COPY forecasting ./forecasting
COPY frontend ./frontend

# The repository is public. Fetch only the runtime assets from Git LFS; never
# copy the full training corpus, raw CWC archive, or original Keras checkpoint
# into this constrained service. The original checkpoint stays available in LFS.
RUN set -eux; \
    git clone --depth 1 --filter=blob:none --no-checkout \
      https://github.com/Rishi122005/Flood_Detection-Prediction.git /tmp/project-assets; \
    git -C /tmp/project-assets lfs install --local; \
    git -C /tmp/project-assets sparse-checkout init --no-cone; \
    printf '%s\n' \
      '/data/glofas/data.grib' \
      '/data/glofas/data.grib.5b7b6.idx' \
      '/models/best_unet_flood.tflite' \
      '/models/best_unet_flood.tflite.json' \
      '/outputs/india/predictions/' \
      '/outputs/before_after_India_1017769/' \
      '/outputs/flood_events/' \
      '/outputs/forecasting/' \
      > /tmp/project-assets/.git/info/sparse-checkout; \
    GIT_LFS_SKIP_SMUDGE=1 git -C /tmp/project-assets checkout main; \
    git -C /tmp/project-assets lfs pull --include='data/glofas/data.grib,models/best_unet_flood.tflite,outputs/india/predictions/*.tif,outputs/before_after_India_1017769/**/*.tif'; \
    mkdir -p /app/data/glofas /app/models /app/outputs; \
    cp -a /tmp/project-assets/data/glofas/. /app/data/glofas/; \
    cp -a /tmp/project-assets/models/best_unet_flood.tflite /app/models/; \
    cp -a /tmp/project-assets/models/best_unet_flood.tflite.json /app/models/; \
    cp -a /tmp/project-assets/outputs/india /app/outputs/; \
    cp -a /tmp/project-assets/outputs/before_after_India_1017769 /app/outputs/; \
    cp -a /tmp/project-assets/outputs/flood_events /app/outputs/; \
    cp -a /tmp/project-assets/outputs/forecasting /app/outputs/; \
    rm -rf /tmp/project-assets; \
    echo '4de69a0d87500cd8e50aae4c3b7fa013d10c4a5fdc39a2525d4f1d3f08993e53  /app/models/best_unet_flood.tflite' | sha256sum --check -; \
    mkdir -p /app/outputs/model_cache; \
    ln -s ../../models/best_unet_flood.tflite /app/outputs/model_cache/best_unet_flood_6f20437ef60a.tflite; \
    python scripts/prepare_hosted_assets.py

EXPOSE 8080
VOLUME ["/app/persistent_uploads"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8080')+'/api/health', timeout=3).read()"
CMD ["sh", "-c", "exec python scripts/run_server.py --host 0.0.0.0 --port ${PORT:-8080}"]
