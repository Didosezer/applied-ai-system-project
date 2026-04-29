from __future__ import annotations

import os
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

_COLLECTION_NAME = "pawpal_kb"
_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
_MODEL_NAME = "all-MiniLM-L6-v2"

_model: SentenceTransformer | None = None
_collection: chromadb.Collection | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(Path(_DB_PATH).resolve()))
        _collection = client.get_or_create_collection(_COLLECTION_NAME)
    return _collection


def _chunk_text(text: str, max_chars: int = 500) -> list[str]:
    """Split markdown text into paragraph-level chunks.

    ## headings are treated as hard boundaries — always start a new chunk,
    regardless of current chunk size. This keeps each section semantically pure.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        is_section_heading = para.startswith("## ")
        if is_section_heading and current:
            chunks.append(current)
            current = para
        elif len(current) + len(para) + 2 <= max_chars:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


def ingest_documents(docs_dir: str) -> int:
    """Read all .md files in docs_dir, embed and upsert into ChromaDB.

    Returns the number of chunks ingested.
    """
    collection = _get_collection()
    model = _get_model()
    total = 0

    for md_file in Path(docs_dir).glob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        chunks = _chunk_text(text)
        for i, chunk in enumerate(chunks):
            doc_id = f"{md_file.stem}__{i}"
            embedding = model.encode(chunk).tolist()
            collection.upsert(
                ids=[doc_id],
                documents=[chunk],
                embeddings=[embedding],
                metadatas=[{"source": md_file.name}],
            )
            total += 1

    return total


def search(query: str, n_results: int = 4) -> list[dict]:
    """Search the knowledge base and return ranked text chunks.

    Each result is a dict with keys: text, source, score.
    Returns an empty list if the collection has no documents.
    """
    collection = _get_collection()
    if collection.count() == 0:
        return []

    model = _get_model()
    embedding = model.encode(query).tolist()
    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({"text": doc, "source": meta.get("source", ""), "score": round(1 - dist, 4)})

    return chunks
