# NOTE ON BUILD CONTEXT: this image needs both api/ and ../data/sample_docs,
# which live in different directories. Docker can only COPY files that are
# inside the "build context" you hand it — it can never reach outside with
# "../". So docker-compose.yml points this service's build "context" at the
# PROJECT ROOT (".") and its "dockerfile" at "api/Dockerfile", and every COPY
# below is written relative to that root, e.g. "COPY api/requirements.txt".
# If you ever run `docker build` by hand instead of via compose, remember to
# run it from the project root: `docker build -f api/Dockerfile .`

# --- Stage 1: "builder" ---
# This stage's only job is to install Python dependencies into a virtualenv.
# It's allowed to be big and messy (it has gcc, build headers, pip caches,
# etc.) because none of that ends up in the final image.
FROM python:3.12-slim AS builder

WORKDIR /app

# Some Python packages (e.g. chromadb's dependencies) need a C compiler to
# build from source if no pre-built wheel matches the platform. Installing
# build-essential here, but NOT in the final stage, is the whole point of a
# multi-stage build: you get the tools you need to build, without shipping
# them in production.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency manifest BEFORE application code. Docker layer caching
# means: if requirements.txt is unchanged, this RUN line's cached result is
# reused and pip doesn't reinstall anything, even if you've changed main.py
# a hundred times since the last build. Reordering this after COPY . would
# invalidate the cache on every single code change — one of the most common
# Docker performance mistakes.
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Stage 2: final runtime image ---
# Starts fresh from a clean slim base. Only the virtualenv (already-built
# dependencies) and the application source get copied in — no compilers, no
# pip cache, no apt package lists. This is typically 200-400MB smaller than
# a single-stage equivalent for a project with compiled dependencies.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY api/app ./app
# Sample docs are baked into the image for convenience (POST /ingest/sample-docs).
# In a real project you'd more likely bind-mount data instead of baking it in.
COPY data/sample_docs ./sample_docs

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
