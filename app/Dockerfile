# A Dockerfile is the recipe for building an image.
# Each instruction creates a layer; Docker caches layers, so we order them
# from "changes rarely" to "changes often".

# 1. Start from an official, small Python image (Debian "slim").
FROM python:3.12-slim

# 2. Sensible Python defaults for containers:
#    - don't write .pyc files, print logs immediately, keep pip quiet and small.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 3. Everything below happens inside /app in the image.
WORKDIR /app

# 4. Install dependencies FIRST. requirements.txt changes rarely, so this layer
#    stays cached and rebuilds after a code change take seconds, not minutes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# 5. Never run your app as root inside the container.
RUN useradd --create-home --uid 10001 appuser

# 6. Copy the application code (see .dockerignore for what is skipped).
COPY --chown=appuser:appuser . .

USER appuser

# 7. Documentation only: the app listens on 8000 *inside* its container.
#    It is NOT published to the server; nginx reaches it over the Docker network.
EXPOSE 8000

# 8. The command the container runs: gunicorn (production web server)
#    with 2 worker processes, logging requests to stdout for `docker logs`.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "main:create_app()"]
