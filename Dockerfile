# Dockerfile for the AuRIS FastAPI backend.
#
# Serves auris.api:app on the port Railway (or any host) assigns via
# $PORT. Do NOT run --reload in production; the host process is our
# process supervisor, and --reload spawns a watcher subprocess that
# would break signal handling and increase memory.
#
# Build:   docker build -t auris:latest .
# Run:     docker run --rm -p 8000:8000 -e GROQ_API_KEY=... auris:latest
#
# The image installs the package in editable mode so any code path
# that reads __file__ (like the CLI + Streamlit .env resolution) still
# behaves the same as local dev.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install runtime deps first (best cache layer). requirements.txt is the
# source of truth for the base engine deps; pyproject only pins the
# same set for editable installs. Keeping them in sync is enforced by
# CI (all tests run against pyproject-installed dependencies).
COPY requirements.txt pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --upgrade pip \
    && pip install -e .

# uvicorn honours $PORT so the same image runs on Railway (which
# injects $PORT) and on a local machine (default 8000). One worker
# is right for Railway's smallest instance; scale up via WEB_CONCURRENCY.
ENV PORT=8000 \
    WEB_CONCURRENCY=1
EXPOSE 8000

# Do NOT bake GROQ_API_KEY into the image. Set it as a Railway env var.
# AURIS_CORS_ORIGINS defaults to "*" for first-boot smoke tests; tighten
# to the Vercel origin as soon as the frontend URL is known.
CMD ["sh", "-c", "uvicorn auris.api:app --host 0.0.0.0 --port ${PORT} --workers ${WEB_CONCURRENCY}"]
