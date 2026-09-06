# ============================================================
#  uryx-api — FastAPI backend
# ============================================================
FROM python:3.11-slim-bookworm AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/models

# libmagic: dosya türü tespiti, libpq: postgres, poppler/tesseract yok (hafif tutuldu)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        libmagic1 \
        libpq5 \
        git \
        gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Bağımlılıklar (katman önbelleği için ayrı) ---
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# RapidOCR → OpenCV; slim imajda libGL yok. Tesseract/poppler yok.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# --- Uygulama ---
COPY apps/api/ /app/

RUN mkdir -p /data/uploads /models && \
    groupadd -r jarvis && useradd -r -g jarvis -d /app jarvis && \
    chown -R jarvis:jarvis /app /data /models

# Docker soketine erişim için (docker araçları). Soketin grup id'si host'a göre
# değişebildiğinden entrypoint içinde dinamik olarak ayarlanır.
COPY docker/api/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).status==200 else 1)"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
