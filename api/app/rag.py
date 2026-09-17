"""
Thin wrapper around a ChromaDB collection running in its own container.

Note the connection: chromadb.HttpClient(host="chroma", ...). "chroma" is not
a hostname that exists anywhere except inside the Docker network created by
docker-compose — it's the *service name* from docker-compose.yml, and Docker's
built-in DNS resolves it to the chroma container's internal IP. This is the
core idea of container networking: services address each other by name, never
by hardcoded IPs, because container IPs change every time a container
restarts.
"""

import os

import chromadb

CHROMA_HOST = os.environ.get("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.environ.get("CHROMA_PORT", "8000"))
COLLECTION_NAME = "docs"


def get_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def get_collection():
    client = get_client()
    # get_or_create so repeated ingests / restarts are idempotent.
    return client.get_or_create_collection(COLLECTION_NAME)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Naive fixed-size chunking with overlap. Good enough for a learning
    project; a real system would chunk on sentence/paragraph boundaries."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c for c in chunks if c.strip()]


def ingest_document(doc_id: str, text: str) -> int:
    """Chunk a document and add it to the collection. Returns chunk count.

    We don't pass explicit embeddings here — Chroma's client library computes
    them locally using a small default embedding model (downloaded once, on
    first use). That download needs outbound network access from the api
    container the first time it runs; after that it's cached in the image
    layer / container filesystem for the life of the container.
    """
    collection = get_collection()
    chunks = chunk_text(text)
    ids = [f"{doc_id}-{i}" for i in range(len(chunks))]
    collection.add(documents=chunks, ids=ids, metadatas=[{"source": doc_id}] * len(chunks))
    return len(chunks)


def retrieve(query: str, n_results: int = 3) -> list[dict]:
    collection = get_collection()
    if collection.count() == 0:
        return []
    results = collection.query(query_texts=[query], n_results=min(n_results, collection.count()))
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    return [{"text": d, "source": m.get("source")} for d, m in zip(docs, metas)]
