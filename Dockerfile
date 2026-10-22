# Aloud for the web: one container, CPU only, no accounts, no cloud.
# Build:  docker build -t aloud-web .
# Run:    docker run -d --name aloud -p 8787:8787 -v "$PWD/data:/data" aloud-web
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ALOUD_DATA_DIR=/data \
    ALOUD_HOST=0.0.0.0 \
    ALOUD_PORT=8787

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu ca-certificates libstdc++6 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 aloud \
    && useradd --uid 1000 --gid aloud --create-home --shell /usr/sbin/nologin aloud \
    && mkdir -p /data && chown aloud:aloud /data

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY web ./web
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && chown -R aloud:aloud /app

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "-m", "server"]
