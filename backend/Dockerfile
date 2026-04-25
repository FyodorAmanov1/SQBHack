# syntax=docker/dockerfile:1.6

# -------- base image ---------------------------------------------------------
# CPU-only image. If you have an NVIDIA GPU on the server, switch the FROM line
# to `nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04` and install python3.11 +
# `pip install --index-url https://download.pytorch.org/whl/cu126 torch torchaudio`
# inside the builder stage.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache/huggingface \
    TRANSFORMERS_CACHE=/app/.cache/huggingface \
    TORCH_HOME=/app/.cache/torch

# System deps:
#   ffmpeg + libavcodec-dev etc. -> PyAV (av) and edge-tts MP3 decode
#   libsndfile1                 -> soundfile
#   git                         -> transformers occasionally clones HF repos
#   ca-certificates, curl       -> HTTPS fetches + healthchecks
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        git \
        ca-certificates \
        curl \
        build-essential \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# -------- python deps --------------------------------------------------------
# Copy requirements first so Docker can cache the (very expensive) wheel install
# layer across code changes.
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# -------- application code ---------------------------------------------------
COPY app ./app

# Directory for auto-converted CT2 Whisper caches (configurable via STT_MODEL_CACHE_DIR).
RUN mkdir -p /app/models/whisper_ct2 /app/.cache/huggingface /app/.cache/torch

EXPOSE 8000

# Healthcheck hits the FastAPI /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

# Single worker: STT/TTS models are heavy; scale horizontally by running more
# containers behind a load balancer rather than adding workers in one container.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
