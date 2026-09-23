# Single stage: the client is vanilla ES modules and Canvas, so there is nothing
# to build. ffmpeg is not optional — it decodes the source FLAC for transcription
# and peaks, and renders the published MP3.
FROM python:3.13-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    SERMON_DATA_ROOT=/data \
    HF_HOME=/models

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# The whisper weights are ~1.5 GB and are NOT baked in: they live on a mounted
# volume so an image rebuild does not re-ship them and a redeploy does not
# re-download them. The first run on a fresh volume fetches them once; set
# HF_HUB_OFFLINE=1 afterwards to refuse any network fetch.
VOLUME ["/data", "/models"]

EXPOSE 8000

# The reviewer's app. The worker runs the same image with `sermon-work`.
CMD ["sermon-serve"]
