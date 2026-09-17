# Dockerized RAG + MCP Agent

A small multi-container system that ties together the two things you've
already explored (RAG, MCP) with the thing you're learning now (Docker):

```
                 ┌──────────────┐
   you  ───HTTP──▶     api      │  FastAPI "agent"
                 │  (port 8000) │  - retrieves context from Chroma
                 └──────┬───────┘  - calls a tool on mcp-server
                        │          - asks Gemini to answer
           agent-net (docker bridge network)
                        │
         ┌──────────────┼───────────────┐
         ▼                              ▼
 ┌───────────────┐             ┌────────────────┐
 │    chroma     │             │   mcp-server   │
 │ vector store  │             │  (calculator,  │
 │ (port 8000)   │             │  word_count)   │
 └───────────────┘             └────────────────┘
```

Three containers, three concerns:
- **chroma** — vector database (official image, no code of yours)
- **mcp-server** — an MCP tool server you wrote, exposed over SSE
- **api** — the agent: does retrieval, calls the MCP tool, calls Gemini

You don't need Docker knowledge going in. This README is a guided build,
in order. Do the parts in sequence — each one only makes sense once the
previous one is running.

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin) installed
- A Gemini API key (for the `/chat` endpoint — everything else works
  without one)

## Part 0 — get the containers running

```bash
cp .env.example .env        # then paste your real ANTHROPIC_API_KEY in
docker compose up --build
```

First run will take a couple of minutes (building images, pulling the
Chroma image, installing Python deps). Leave this terminal open — you'll see
interleaved logs from all three containers, prefixed by service name. That
prefix is one of the first genuinely useful things compose gives you: in a
3+ container app, `docker compose logs -f api` to isolate just one service's
logs is something you'll use constantly.

In a second terminal, check everything's healthy:

```bash
docker compose ps
```

You should see three services, `chroma` and the containers with a
`(healthy)` status once their HEALTHCHECKs have passed a few times.

**What just happened, concept by concept:**
- `docker compose up` read `docker-compose.yml`, and for each service either
  pulled an image (`chroma`) or built one from a Dockerfile (`api`,
  `mcp-server`).
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

`GET /tools` calls `mcp_client.list_tools()`, which opens an SSE connection
to `mcp-server` — proof `api` can reach a container it never mentions by IP,
only by the name `mcp-server`, because that's the service name in
`docker-compose.yml`.

## Part 2 — read the Dockerfiles

Now that you've seen it work, read `mcp_server/Dockerfile` (simple,
single-stage) then `api/Dockerfile` (multi-stage). Both are heavily
commented — that's where most of the "why", not just "what", lives. Key
ideas to walk away with:

1. **Layer caching** — instructions are cached in order; put things that
   change rarely (installing dependencies) before things that change often
   (your source code).
2. **Multi-stage builds** — build tools live in a throwaway "builder" stage;
   only the compiled result gets copied into the final image. Compare image
   sizes yourself:
   ```bash
   docker images | grep docker-rag-mcp-agent
   ```
3. **Non-root users** — both images create and switch to an unprivileged
   user before running the app.
4. **Healthchecks** — how compose knows a service is actually ready, not
   just "started" (see `depends_on: condition: service_healthy` for `chroma`
   in docker-compose.yml).
5. **Build context** — `api/Dockerfile`'s top comment explains why its
   `context:` in docker-compose.yml is `.` (project root), not `./api`.

## Part 3 — break it on purpose

The fastest way to actually learn Docker is to watch it fail correctly.
Try each of these and think about *why* before reading the answer:

- Stop `chroma` only: `docker compose stop chroma`, then hit `/chat` again.
  <details><summary>What happens / why</summary>
  The api container's retrieval call fails because it can no longer reach
  chroma:8000 — connection refused. This is why real systems add retries
  and circuit breakers around inter-service calls; a single dependency going
  down shouldn't necessarily crash the whole request.
  </details>

- Edit `mcp_server/server.py` (e.g. add a `print` statement), then
  `docker compose up --build mcp-server`, without rebuilding `api`.
  <details><summary>What happens / why</summary>
  Only the mcp-server image rebuilds — its Dockerfile layer for `COPY
  server.py .` is invalidated but api's image build cache is untouched. This
  is the payoff of splitting services into separate Dockerfiles instead of
  one giant container.
  </details>

- Run `docker compose down -v` (note the `-v`), then `docker compose up`,
  then try `/chat` before re-ingesting.
  <details><summary>What happens / why</summary>
  `-v` removes the named volume too, so chroma_data is gone and your
  ingested documents with it. Retrieval returns nothing. This demonstrates
  the volume, not the container, is what held your data.
  </details>

## Part 4 — extend it yourself

Pick at least one, since a from-scratch extension is what actually makes
this a portfolio piece rather than a tutorial you followed:

- **Add a Redis container** for conversation history/caching. New service in
  compose, new env var on `api`, a couple lines with `redis-py`. Forces you
  to practice adding a fourth service to an existing network from scratch.
- **Add a new MCP tool** (e.g. a stub "web_search" tool, or one that reads
  the sample docs directory) and call it conditionally from `/chat`.
- **Add resource limits** to each service in compose (`deploy.resources.limits`)
  and watch what happens to a container that exceeds its memory limit.
- **Push images to GitHub Container Registry** via the existing GitHub
  Actions workflow (`.github/workflows/docker-build.yml` currently only
  builds — extend it to also `docker/login-action` + push on `main`).
- **Add a `docker-compose.prod.yml` override** that removes bind-mounted
  source (if you add one for live-reload dev) and sets `restart: unless-stopped`.

## Repo layout

```
docker-rag-mcp-agent/
├── docker-compose.yml       # orchestrates all three services
├── .env.example             # copy to .env, add your API key
├── api/
│   ├── Dockerfile            # multi-stage build, heavily commented
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI endpoints: /health /ingest /chat /tools
│       ├── rag.py            # Chroma client wrapper
│       └── mcp_client.py     # MCP SSE client used by /chat and /tools
├── mcp_server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── server.py             # FastMCP tool server: calculator, word_count
├── data/sample_docs/         # sample text ingested by /ingest/sample-docs
└── .github/workflows/        # CI: builds both images on every push
```

## For your portfolio

When you write this up (README on GitHub is often enough, but a short blog
post travels further), the story worth telling isn't "I used Docker" — it's:
*three independently-built services, wired together over a Docker network,
each with its own Dockerfile, healthcheck, and failure mode, orchestrated
with one compose file.* That's a materially different (and more hireable)
claim than "I containerized a script."
