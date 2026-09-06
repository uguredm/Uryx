# ============================================================
#  uryx-tts — Piper TTS servisi (CPU)
# ============================================================
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIPER_VOICE_DIR=/voices

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        espeak-ng \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/tts/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/tts/ /app/

RUN mkdir -p /voices

EXPOSE 8091

HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=20 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8091", "--no-access-log"]
