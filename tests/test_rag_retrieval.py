import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import chromadb
import pytest
import tools.rag_retrieval as rag


@pytest.fixture(autouse=True)
def isolated_rag(monkeypatch):
    """Give each test its own in-memory ChromaDB collection."""
    client = chromadb.Client()
    col = client.get_or_create_collection("pawpal_test_kb")
    monkeypatch.setattr(rag, "_collection", col)
    yield col
    monkeypatch.setattr(rag, "_collection", None)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def test_chunk_text_section_heading_is_hard_boundary():
    chunks = rag._chunk_text("## Section A\nSome text here.\n\n## Section B\nOther text.")
    assert any("Section A" in c for c in chunks)
    assert any("Section B" in c for c in chunks)
    assert not any("Section A" in c and "Section B" in c for c in chunks)


def test_chunk_text_short_text_single_chunk():
    chunks = rag._chunk_text("Hello world.")
    assert chunks == ["Hello world."]


def test_chunk_text_respects_max_chars():
    # Multiple paragraphs: chunker should not merge them if combined size > max_chars
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    chunks = rag._chunk_text(text, max_chars=30)
    assert len(chunks) >= 2
    assert all(len(c) <= 60 for c in chunks)


# ---------------------------------------------------------------------------
# Ingest + search
# ---------------------------------------------------------------------------

def test_ingest_and_search_returns_results(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "care_dogs.md").write_text(
        "## Dog Care\nGolden Retriever needs daily exercise and weight management."
    )
    rag.ingest_documents(str(kb))
    results = rag.search("Golden Retriever exercise")
    assert len(results) >= 1


def test_search_result_schema(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "care_cats.md").write_text("## Cat Care\nPersian cats need daily brushing.")
    rag.ingest_documents(str(kb))
    results = rag.search("Persian cat brushing")
    for r in results:
        assert "text" in r
        assert "source" in r
        assert "score" in r


def test_search_empty_collection_returns_empty(monkeypatch):
    # Use a brand-new isolated collection guaranteed to be empty
    fresh_col = chromadb.Client().get_or_create_collection("pawpal_empty_col")
    monkeypatch.setattr(rag, "_collection", fresh_col)
    results = rag.search("anything")
    assert results == []


def test_ingest_documents_returns_chunk_count(tmp_path):
    kb = tmp_path / "kb"
    kb.mkdir()
    (kb / "test.md").write_text("## Section\nSome content here.")
    count = rag.ingest_documents(str(kb))
    assert isinstance(count, int)
    assert count >= 1
