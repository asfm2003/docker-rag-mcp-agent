import os
from pathlib import Path

from google import genai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import mcp_client, rag

app = FastAPI(title="RAG + MCP Agent")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# genai.Client() also auto-reads the GEMINI_API_KEY env var on its own if you
# don't pass api_key= explicitly; passing it here just makes the "did I set
# my .env correctly" failure mode (see the check in /chat below) explicit
# instead of the client silently doing nothing.
_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


class ChatRequest(BaseModel):
    query: str
    use_calculator: bool = False


class IngestRequest(BaseModel):
    doc_id: str
    text: str


@app.get("/health")
def health():
    """Liveness/readiness endpoint — this is what the Dockerfile HEALTHCHECK
    and docker-compose's service_healthy condition poll."""
    return {"status": "ok"}


@app.post("/ingest")
def ingest(req: IngestRequest):
    n_chunks = rag.ingest_document(req.doc_id, req.text)
    return {"doc_id": req.doc_id, "chunks_added": n_chunks}


@app.post("/ingest/sample-docs")
def ingest_sample_docs():
    """Convenience endpoint: loads the .txt files bundled in /app/sample_docs
    (mounted from ../data/sample_docs) so you have something to query
    immediately without writing your own ingestion client."""
    sample_dir = Path("/app/sample_docs")
    if not sample_dir.exists():
        raise HTTPException(404, "sample_docs directory not mounted")
    results = {}
    for f in sample_dir.glob("*.txt"):
        text = f.read_text()
        results[f.name] = rag.ingest_document(f.stem, text)
    return {"ingested": results}


@app.get("/tools")
async def tools():
    """Lists tools currently exposed by the MCP server container — proof the
    api container can reach it over the Docker network."""
    return {"tools": await mcp_client.list_tools()}


@app.post("/chat")
async def chat(req: ChatRequest):
    if _client is None:
        raise HTTPException(
            500,
            "GEMINI_API_KEY is not set. Add it to your .env file (see .env.example).",
        )

    # 1. Retrieve relevant context from the vector store (Chroma container).
    retrieved = rag.retrieve(req.query)
    context = "\n\n".join(f"[{r['source']}] {r['text']}" for r in retrieved) or "(no matching documents found)"

    # 2. Optionally call out to a tool on the MCP server container.
    tool_result = None
    if req.use_calculator:
        tool_result = await mcp_client.call_tool("calculator", {"expression": req.query})

    # 3. Ask the model to answer using the retrieved context (+ tool result).
    system_prompt = (
        "Answer the user's question using ONLY the information given to you below: "
        "the retrieved document context and, if present, a tool result. "
        "A tool result (e.g. a calculator output) is a valid, sufficient basis for "
        "your answer on its own, even if the document context is unrelated to it. "
        "If neither the context nor any tool result contains the answer, say so explicitly."
    )
    user_content = f"Context:\n{context}\n\n"
    if tool_result is not None:
        user_content += f"Tool result (calculator): {tool_result}\n\n"
    user_content += f"Question: {req.query}"

    response = _client.interactions.create(
        model=MODEL,
        system_instruction=system_prompt,
        input=user_content,
    )
    answer = response.output_text

    return {
        "answer": answer,
        "retrieved_context": retrieved,
        "tool_result": tool_result,
    }
