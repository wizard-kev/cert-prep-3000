# CCST prep app. Image tags are pinned (SR11).
FROM python:3.14.8-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY src/ ./src/

# Run as an unprivileged user; /data is the only writable path (mounted at runtime).
RUN useradd --create-home --uid 10001 app && mkdir -p /data && chown app:app /data
USER app

ENV CCST_OBJECTIVES_DIR=/app/objectives \
    CCST_DATA_DIR=/data \
    OLLAMA_URL=http://ollama:11434

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/chapters', timeout=4).status == 200 else 1)"

# 0.0.0.0 inside the container only; Compose publishes it on the host's 127.0.0.1 (SR10).
CMD ["python", "-m", "uvicorn", "ccst.main:app", "--app-dir", "src", "--host", "0.0.0.0", "--port", "8000"]
