# Learning walkthrough

This is the guided, step-by-step version of building and running this project —
written for learning Docker by doing, not for someone evaluating the finished
result (see the main [README](../README.md) for that). Do the parts in order;
each one assumes the previous one is running.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) installed
- A Gemini API key (for the `/chat` endpoint — everything else works without one)

## Part 0 — get the containers running

```bash
cp .env.example .env        # then paste your real GEMINI_API_KEY in
docker compose up --build
```

First run takes a couple of minutes (building images, pulling the Chroma image,
installing Python deps). In a second terminal, check everything's healthy:

```bash
docker compose ps
```

You should see three services, with `(healthy)` once their HEALTHCHECKs have
passed a few times.

**What just happened, concept by concept:**
- `docker compose up` read `docker-compose.yml`, and for each service either
  pulled an image (`chroma`) or built one from a Dockerfile (`api`, `mcp-server`).
- It created one shared network (`agent-net`) and attached all three
  containers to it, so they can reach each other by service name.
- It created a named volume (`chroma_data`) for Chroma's storage, so if you
  stop and restart the stack, your ingested documents are still there.

Try killing it and bringing it back to prove that to yourself:

```bash
docker compose down       # stops and removes containers, keeps the volume
docker compose up -d      # -d = detached, runs in the background
```

## Part 1 — ingest some documents and ask a question

```bash
curl -X POST http://localhost:8000/ingest/sample-docs
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What does a Docker healthcheck do?"}'
```

You should get back an answer, plus the retrieved chunks it was grounded in.
That request just crossed all three containers: `api` queried `chroma` over
the network, then called Gemini, using only context Chroma returned.

Now try the MCP tool path:

```bash
curl http://localhost:8000/tools
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "(14 + 8) * 3", "use_calculator": true}'
```

`GET /tools` opens an SSE connection to `mcp-server` — proof `api` can reach a
container it never mentions by IP, only by the name `mcp-server`, because
that's the service name in `docker-compose.yml`.

## Part 2 — read the Dockerfiles

Read `mcp_server/Dockerfile` (simple, single-stage) then `api/Dockerfile`
(multi-stage). Both are heavily commented. Key ideas to walk away with:

1. **Layer caching** — instructions are cached in order; put things that
   change rarely (installing dependencies) before things that change often
   (your source code).
2. **Multi-stage builds** — build tools live in a throwaway "builder" stage;
   only the compiled result gets copied into the final image.
3. **Non-root users** — both images create and switch to an unprivileged
   user before running the app.
4. **Healthchecks** — how compose knows a service is actually ready, not
   just "started."
5. **Build context** — `api/Dockerfile`'s top comment explains why its
   `context:` in docker-compose.yml is `.` (project root), not `./api`.

## Part 3 — break it on purpose

The fastest way to actually learn Docker is to watch it fail correctly.

- **Stop `chroma` only**: `docker compose stop chroma`, then hit `/chat`
  again. The api container's retrieval call fails — connection refused —
  because it can no longer reach `chroma:8000`. Real systems add retries and
  circuit breakers around calls like this so one dependency going down
  doesn't take out the whole request. Bring it back with
  `docker compose start chroma` and confirm it recovers.
- **Edit `mcp_server/server.py`**, then `docker compose up --build mcp-server`,
  without touching `api`. Only the mcp-server image rebuilds — its Dockerfile
  layer for `COPY server.py .` is invalidated but `api`'s image build cache
  is untouched. That's the payoff of splitting services into separate
  Dockerfiles instead of one giant container.
- **Run `docker compose down -v`** (note the `-v`), bring it back up, and try
  `/chat` before re-ingesting. `-v` removes the named volume too, so
  `chroma_data` is gone and your ingested documents with it — proof the
  volume, not the container, is what held your data.

## Real bugs hit while building this (and how they were diagnosed)

These weren't scripted — they're the actual errors that came up, kept here
because working through them is most of the real learning:

1. **Wrong build context for `mcp-server`.** Its Dockerfile did
   `COPY requirements.txt .`, but compose pointed its `context:` at the
   project root, where that file doesn't exist. Fixed by scoping its context
   to `./mcp_server` — it doesn't need files outside its own folder the way
   `api` does.
2. **`chromadb` client/server version mismatch.** `api`'s `requirements.txt`
   had `chromadb>=0.5.0` (unpinned), while the `chroma` service ran a fixed
   `chromadb/chroma:0.5.20`. An unpinned install grabbed a newer client that
   spoke a slightly different wire protocol, and the server crashed on
   `KeyError: '_type'`. Fixed by pinning `chromadb==0.5.20` to match exactly.
3. **`mcp` v2 breaking changes.** The `mcp` Python package released a major
   v2 that renamed `FastMCP` to `MCPServer` and changed several APIs. An
   unpinned `mcp>=1.2.0` grabbed v2 and crashed on import. Fixed by pinning
   `mcp>=1.2.0,<2` in both services — the migration guide itself recommends
   this until you deliberately port to v2.
4. **A prompt logic bug, not a Docker bug.** The system prompt told Gemini to
   answer using only "the provided context," meaning the retrieved documents
   — but tool results were a separate section it wasn't told it could rely
   on. Asking `(14 + 8) * 3` with the calculator on returned a correct tool
   result (`66`) but an answer of "not present in context." Fixed by
   rewording the prompt to explicitly say a tool result is a sufficient
   basis for the answer on its own.

## Extend it yourself

Pick at least one, since a from-scratch extension is what actually makes
this a portfolio piece rather than a tutorial you followed:

- **Add a Redis container** for conversation history/caching.
- **Add a new MCP tool** and call it conditionally from `/chat`.
- **Add resource limits** to each service in compose and watch what happens
  to a container that exceeds its memory limit.
- **Push images to GitHub Container Registry** via the existing GitHub
  Actions workflow.
- **Add retries/circuit-breaking** around the `chroma` and `mcp-server`
  calls in `main.py`, so a dependency outage degrades gracefully instead of
  500ing (see Part 3's first exercise).
