# syntax=docker/dockerfile:1

# Slim base: small image, no compiler toolchain shipped to production.
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE keeps .pyc files out of the image.
# PYTHONUNBUFFERED makes logs appear immediately in `docker compose logs`.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies are copied and installed before the application code so that
# this layer stays cached when only main.py changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code.
COPY main.py ./

# Create the unprivileged runtime user.
#
# /data is created and chowned HERE, while the image is still being built.
# When Docker first creates the named volume and mounts it at /data, it seeds
# the empty volume from the image's /data directory, ownership included. If
# /data did not exist in the image, the volume would be created root-owned and
# the non-root process could not open the SQLite file.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app

USER appuser

# Documents the internal port. Publishing is deliberately left to Compose,
# and only nginx is published to the host.
EXPOSE 8000

# Uses the standard library so the image does not need curl installed.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"

# Exec form, no --reload: one process, signals reach uvicorn, no file watcher.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
