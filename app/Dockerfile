# syntax=docker/dockerfile:1
#
# Build from the repository root so migrations ship in the same image:
#   docker build -f app/Dockerfile -t items-api .

# Slim base: small image, no compiler toolchain shipped to production.
FROM python:3.15-slim

# Set by the release workflow from the Git tag; local builds report the code default.
ARG APP_VERSION=1.5.0-local
ARG APP_REVISION=unknown
LABEL org.opencontainers.image.title="cloud-native-items-api" \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$APP_REVISION \
      org.opencontainers.image.source="https://github.com/Alan-911/Cloud-Computing"

# PYTHONDONTWRITEBYTECODE keeps .pyc files out of the image.
# PYTHONUNBUFFERED makes logs appear immediately in `docker compose logs`.
# APP_VERSION makes /api/health report the version of the running image.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_ENVIRONMENT=production \
    APP_VERSION=$APP_VERSION

WORKDIR /srv

# Apply Debian security fixes released after the base image was built (e.g. a
# zlib CVE flagged by the image scan). The Trivy gate in security.yml catches
# any fixable HIGH/CRITICAL package this misses.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Dependencies first so this layer stays cached when only code changes.
# pip and CPython's bundled ensurepip wheels are only needed to install, so they
# are removed afterwards: they carry their own vendored copies of urllib3,
# msgpack and setuptools that the image scanner flags, and nothing at runtime
# uses them. (Same RUN, so they never persist in a layer.)
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m pip uninstall -y pip \
    && rm -rf /usr/local/lib/python3.*/ensurepip

# Application package and the migrations that own its schema.
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

# Unprivileged runtime user. Nothing in the image is writable by it except its
# home directory; all state lives in PostgreSQL.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser
USER appuser

# Documents the internal port. Publishing is left to Compose, and only nginx
# is published to the host.
EXPOSE 8000

# Liveness only: a database outage should not mark the container unhealthy and
# trigger restarts. Readiness (/api/health) is what nginx and probes use.
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health/live', timeout=2).status == 200 else 1)"

# Exec form, no --reload: one process, signals reach uvicorn, no file watcher.
# --no-access-log: the app writes its own JSON access log with request IDs.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-access-log"]
