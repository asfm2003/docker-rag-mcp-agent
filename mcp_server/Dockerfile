# --- MCP tool server image ---
# Small, single-stage build: this service has few dependencies, so a
# multi-stage split (see ../api/Dockerfile for that pattern) isn't worth the
# extra complexity here. Match build complexity to the actual problem.

FROM python:3.12-slim

# Prevents Python from writing .pyc files and buffering stdout — the latter
# matters in Docker specifically, because buffered logs can vanish or arrive
# late when a container is killed, which makes `docker logs` unreliable.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only the requirements file first. Docker caches each layer by the hash
# of its inputs — as long as requirements.txt doesn't change, this pip
# install layer is reused on every rebuild even if server.py changes,
# which is the single biggest thing you can do for fast rebuild times.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

# Run as a non-root user inside the container. If this container is ever
# compromised via a dependency vulnerability, the attacker doesn't get root
# inside the container (and, on misconfigured hosts, potentially the host).
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8100

# A healthcheck lets `docker ps`, `docker compose ps`, and other services'
# `depends_on: condition: service_healthy` know this is actually accepting
# connections, not just that the process started.
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/sse', timeout=2)" || exit 1

CMD ["python", "server.py"]
