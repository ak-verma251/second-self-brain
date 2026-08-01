"""
Tests for the SecondSelf embedding engine (Step 2.6).

All tests use an isolated temporary ChromaDB so they never touch
the real data/chroma/ directory.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture()
def engine(tmp_path):
    """Provide an EmbeddingEngine backed by a temp ChromaDB directory."""
    chroma_dir = tmp_path / "chroma"
    chroma_dir.mkdir()

    with patch("secondself.embed.CHROMA_DIR", chroma_dir):
        from secondself.embed import EmbeddingEngine
        yield EmbeddingEngine()


@pytest.fixture()
def populated_engine(engine):
    """EmbeddingEngine pre-loaded with 3 semantically distinct notes."""
    engine.store(
        "note-ml",
        "Machine learning trains models using gradient descent and backpropagation",
        {"category": "resources", "title": "Machine Learning Basics", "tags": "[]"},
    )
    engine.store(
        "note-transformer",
        "Transformers use self-attention mechanisms instead of recurrence for NLP tasks",
        {"category": "resources", "title": "Transformer Architecture", "tags": "[]"},
    )
    engine.store(
        "note-cooking",
        "Sourdough bread requires a live starter culture of wild yeast and bacteria",
        {"category": "areas", "title": "Sourdough Bread", "tags": "[]"},
    )
    return engine


# ─── embed_text() ─────────────────────────────────────────────────────────────


class TestEmbedText:
    def test_produces_384_dim_vector(self, engine):
        """embed_text must return exactly 384 floats (all-MiniLM-L6-v2)."""
        vec = engine.embed_text("Hello world")
        assert len(vec) == 384

    def test_returns_list_of_floats(self, engine):
        """All elements in the vector must be plain Python floats."""
        vec = engine.embed_text("Test sentence")
        assert isinstance(vec, list)
        assert all(isinstance(v, float) for v in vec)

    def test_different_texts_produce_different_vectors(self, engine):
        """Two different sentences must produce non-identical vectors."""
        vec1 = engine.embed_text("Machine learning is fascinating")
        vec2 = engine.embed_text("Sourdough bread needs a starter")
        assert vec1 != vec2

    def test_same_text_produces_same_vector(self, engine):
        """The same text must always produce the same vector (deterministic)."""
        vec1 = engine.embed_text("Repeated sentence for consistency check")
        vec2 = engine.embed_text("Repeated sentence for consistency check")
        assert vec1 == vec2

    def test_normalized_vector(self, engine):
        """Vectors should be unit-normalized (magnitude ≈ 1.0)."""
        import math
        vec = engine.embed_text("Normalization test")
        magnitude = math.sqrt(sum(v ** 2 for v in vec))
        assert abs(magnitude - 1.0) < 1e-4  # within floating-point tolerance


# ─── store() ─────────────────────────────────────────────────────────────────


class TestStore:
    def test_store_increases_count(self, engine):
        """Storing a note should increase the collection count by 1."""
        assert engine.collection.count() == 0
        engine.store("id-1", "Some text", {"category": "resources"})
        assert engine.collection.count() == 1

    def test_store_multiple_notes(self, engine):
        """Storing N notes should result in exactly N items in the collection."""
        for i in range(5):
            engine.store(f"id-{i}", f"Note number {i}", {"category": "resources"})
        assert engine.collection.count() == 5

    def test_upsert_same_id_does_not_duplicate(self, engine):
        """Calling store() twice with the same ID should overwrite, not duplicate."""
        engine.store("same-id", "First version of text", {"category": "resources"})
        engine.store("same-id", "Updated version of text", {"category": "resources"})
        assert engine.collection.count() == 1

    def test_metadata_list_serialized_to_string(self, engine):
        """list values in metadata must be stored as JSON strings (ChromaDB constraint)."""
        engine.store(
            "meta-test",
            "Some content",
            {"tags": ["ai", "nlp"], "category": "resources"},
        )
        fetched = engine.collection.get(ids=["meta-test"], include=["metadatas"])
        stored_tags = fetched["metadatas"][0]["tags"]
        # Should be a JSON string like '["ai", "nlp"]', not a list
        assert isinstance(stored_tags, str)
        import json
        assert json.loads(stored_tags) == ["ai", "nlp"]

    def test_store_retrieves_correct_document(self, engine):
        """The stored document text must be retrievable from ChromaDB."""
        engine.store("doc-id", "My exact document text", {"category": "resources"})
        fetched = engine.collection.get(ids=["doc-id"], include=["documents"])
        assert fetched["documents"][0] == "My exact document text"


# ─── query_similar() ─────────────────────────────────────────────────────────


class TestQuerySimilar:
    def test_returns_results(self, populated_engine):
        """query_similar should return non-empty results when notes exist."""
        results = populated_engine.query_similar("deep learning", k=3)
        assert len(results) > 0

    def test_result_structure(self, populated_engine):
        """Each result must have the 4 required keys."""
        results = populated_engine.query_similar("machine learning", k=1)
        assert len(results) == 1
        result = results[0]
        assert "id" in result
        assert "document" in result
        assert "metadata" in result
        assert "similarity" in result

    def test_similarity_is_float_in_range(self, populated_engine):
        """Similarity score must be a float between 0 and 1 (inclusive)."""
        results = populated_engine.query_similar("neural networks", k=3)
        for r in results:
            assert isinstance(r["similarity"], float)
            assert 0.0 <= r["similarity"] <= 1.0

    def test_sorted_by_descending_similarity(self, populated_engine):
        """Results must be ordered from most to least similar."""
        results = populated_engine.query_similar("transformer attention NLP", k=3)
        similarities = [r["similarity"] for r in results]
        assert similarities == sorted(similarities, reverse=True)

    def test_relevant_note_ranks_higher(self, populated_engine):
        """A semantically relevant note should rank above an unrelated one."""
        results = populated_engine.query_similar("self-attention NLP transformers", k=3)
        ids = [r["id"] for r in results]
        # transformer note should rank above the cooking note
        assert ids.index("note-transformer") < ids.index("note-cooking")

    def test_empty_collection_returns_empty_list(self, engine):
        """query_similar on an empty collection must return [] not crash."""
        results = engine.query_similar("anything", k=5)
        assert results == []

    def test_k_limits_results(self, populated_engine):
        """query_similar(k=1) must return at most 1 result."""
        results = populated_engine.query_similar("machine learning", k=1)
        assert len(results) <= 1

    def test_k_larger_than_collection_is_safe(self, populated_engine):
        """Requesting more results than items in the collection must not crash."""
        # Collection has 3 items, asking for 100
        results = populated_engine.query_similar("learning", k=100)
        assert len(results) == 3  # capped at actual collection size


# ─── query_similar_by_id() ───────────────────────────────────────────────────


class TestQuerySimilarById:
    def test_excludes_self(self, populated_engine):
        """The source note itself must NOT appear in results."""
        results = populated_engine.query_similar_by_id("note-ml", k=5)
        ids = [r["id"] for r in results]
        assert "note-ml" not in ids

    def test_returns_other_notes(self, populated_engine):
        """Results must contain notes other than the source."""
        results = populated_engine.query_similar_by_id("note-ml", k=2)
        assert len(results) > 0

    def test_k_respected(self, populated_engine):
        """query_similar_by_id(k=1) must return at most 1 result."""
        results = populated_engine.query_similar_by_id("note-ml", k=1)
        assert len(results) <= 1

    def test_raises_on_unknown_id(self, populated_engine):
        """Querying a non-existent ID must raise ValueError."""
        with pytest.raises(ValueError, match="not found in the ChromaDB collection"):
            populated_engine.query_similar_by_id("does-not-exist", k=3)

    def test_similar_notes_rank_higher_than_unrelated(self, populated_engine):
        """ML note should be more similar to transformer note than to cooking note."""
        results = populated_engine.query_similar_by_id("note-ml", k=2)
        ids = [r["id"] for r in results]
        if "note-cooking" in ids and "note-transformer" in ids:
            assert ids.index("note-transformer") < ids.index("note-cooking")
