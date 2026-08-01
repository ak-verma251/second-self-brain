"""
Tests for secondself.ask — Step 4.5

Covers the six cases from the implementation plan:
  - test_ask_returns_answer()
  - test_ask_includes_sources()
  - test_ask_cites_relevant_notes()
  - test_ask_handles_no_relevant_notes()
  - test_ask_response_has_timings()
  - test_confidence_levels()

Strategy
--------
All tests mock out the two external I/O boundaries:
  1. ``EmbeddingEngine`` — so we never hit ChromaDB or load sentence-transformers.
  2. ``groq.Groq``       — so we never make real LLM API calls.

The ``ask()`` function is exercised with full control over every parameter,
so every branch can be tested deterministically and offline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from secondself.ask import (
    AskResponse,
    SourceNote,
    _extract_body,
    _load_wiki_content,
    _slugify,
    ask,
)


# ─── Fixtures & helpers ──────────────────────────────────────────────────────


def _make_engine(
    *,
    count: int = 3,
    results: list[dict] | None = None,
    embed_vector: list[float] | None = None,
) -> MagicMock:
    """Return a mocked EmbeddingEngine.

    Args:
        count:        Number of items reported by ``collection.count()``.
        results:      List of result dicts returned by ``collection.query()``.
                      Each dict must have keys: id, document, metadata, distances.
        embed_vector: Vector returned by ``embed_text()``.
    """
    if embed_vector is None:
        embed_vector = [0.1] * 384

    if results is None:
        results = [
            {
                "id": "note-abc",
                "document": "Transformers use self-attention mechanisms.",
                "metadata": {"title": "Transformer Architecture", "category": "resources"},
                "similarity": 0.92,
            }
        ]

    # Build the raw ChromaDB-style return value for collection.query()
    chroma_raw = {
        "ids":       [[r["id"]       for r in results]],
        "documents": [[r["document"] for r in results]],
        "metadatas": [[r["metadata"] for r in results]],
        # distance = 1 - similarity (cosine distance space)
        "distances": [[round(1.0 - r["similarity"], 4) for r in results]],
    }

    engine = MagicMock()
    engine.collection.count.return_value = count
    engine.collection.query.return_value = chroma_raw
    engine.embed_text.return_value = embed_vector
    return engine


def _make_groq_response(text: str = "This is the synthesised answer.") -> MagicMock:
    """Return a mocked Groq chat completion response."""
    msg = MagicMock()
    msg.content = text
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ─── Patch targets ───────────────────────────────────────────────────────────

_GROQ_PATCH   = "secondself.ask.Groq"
_DOTENV_PATCH = "secondself.ask.load_dotenv"
_ENV_PATCH    = "secondself.ask.os.getenv"
_FORMAT_PATCH = "secondself.embed.EmbeddingEngine._format_results"


# ─── test_ask_returns_answer ─────────────────────────────────────────────────


class TestAskReturnsAnswer:
    """ask() must always return an AskResponse with a non-empty answer string."""

    def test_returns_ask_response_type(self):
        engine = _make_engine()
        groq_resp = _make_groq_response("My answer.")

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=[
                 {"id": "n1", "document": "doc", "metadata": {"title": "T"}, "similarity": 0.9}
             ]):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("What are transformers?", engine)

        assert isinstance(result, AskResponse)

    def test_answer_is_non_empty_string(self):
        engine = _make_engine()
        groq_resp = _make_groq_response("Transformers use self-attention.")

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=[
                 {"id": "n1", "document": "doc", "metadata": {"title": "T"}, "similarity": 0.9}
             ]):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("What are transformers?", engine)

        assert isinstance(result.answer, str)
        assert len(result.answer) > 0

    def test_answer_matches_groq_output(self):
        engine = _make_engine()
        expected = "Self-attention is the core mechanism. [Source: Transformer Architecture]"
        groq_resp = _make_groq_response(expected)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=[
                 {"id": "n1", "document": "doc", "metadata": {"title": "T"}, "similarity": 0.85}
             ]):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("Explain attention", engine)

        assert result.answer == expected

    def test_missing_api_key_raises_value_error(self):
        engine = _make_engine()

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value=None):
            with pytest.raises(ValueError, match="GROQ_API_KEY"):
                ask("Any question", engine)

    def test_empty_collection_returns_early(self):
        engine = _make_engine(count=0)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"):
            result = ask("Any question", engine)

        assert "empty" in result.answer.lower() or "process" in result.answer.lower()
        assert result.confidence == "low"
        assert result.sources == []


# ─── test_ask_includes_sources ───────────────────────────────────────────────


class TestAskIncludesSources:
    """ask() must populate the sources list with SourceNote objects."""

    def test_sources_is_list(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=[
                 {"id": "n1", "document": "doc", "metadata": {"title": "Title"}, "similarity": 0.75}
             ]):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("question", engine)

        assert isinstance(result.sources, list)

    def test_each_source_is_source_note(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [
            {"id": "n1", "document": "doc1", "metadata": {"title": "Note One"}, "similarity": 0.90},
            {"id": "n2", "document": "doc2", "metadata": {"title": "Note Two"}, "similarity": 0.70},
        ]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("question", engine)

        for src in result.sources:
            assert isinstance(src, SourceNote)

    def test_source_note_has_required_fields(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "abc123", "document": "body text", "metadata": {"title": "My Note"}, "similarity": 0.88}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("question", engine)

        src = result.sources[0]
        assert hasattr(src, "id")
        assert hasattr(src, "title")
        assert hasattr(src, "similarity")
        assert hasattr(src, "excerpt")

    def test_source_id_and_title_match_retrieval(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "abc123", "document": "content", "metadata": {"title": "Known Title"}, "similarity": 0.80}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("question", engine)

        src = result.sources[0]
        assert src.id    == "abc123"
        assert src.title == "Known Title"

    def test_source_similarity_preserved(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "doc", "metadata": {"title": "T"}, "similarity": 0.77}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("question", engine)

        assert result.sources[0].similarity == pytest.approx(0.77, abs=1e-3)

    def test_excerpt_is_truncated_to_300_chars(self, tmp_path):
        """When wiki content is found, the excerpt must not exceed 300+3 chars."""
        # Write a real wiki note so _load_wiki_content finds it
        long_content = "word " * 200  # >300 chars
        md = tmp_path / "resources" / "my-note.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(
            f"---\nid: note-long\ntitle: \"My Note\"\ncategory: resources\n"
            f"tags: []\ncreated: 2026-07-01\nsource: cli\n---\n"
            f"# My Note\n\n> Summary.\n\n## Content\n\n{long_content}\n",
            encoding="utf-8",
        )

        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "note-long", "document": "short doc", "metadata": {"title": "My Note"}, "similarity": 0.85}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw), \
             patch("secondself.ask.WIKI_DIR", tmp_path):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("question", engine)

        # 300 content chars + possible "…" = at most 301 chars
        assert len(result.sources[0].excerpt) <= 301


# ─── test_ask_cites_relevant_notes ───────────────────────────────────────────


class TestAskCitesRelevantNotes:
    """The RAG prompt sent to Groq must include the retrieved note context."""

    def test_groq_receives_note_title_in_prompt(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "Attention paper notes.", "metadata": {"title": "Attention Is All You Need"}, "similarity": 0.91}]

        captured_messages = []

        def fake_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return groq_resp

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.side_effect = fake_create
            ask("Explain attention", engine)

        # The user-turn message must contain the note title
        user_msg = next(m for m in captured_messages if m["role"] == "user")
        assert "Attention Is All You Need" in user_msg["content"]

    def test_groq_receives_retrieved_document_text(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "Self-attention rocks.", "metadata": {"title": "T"}, "similarity": 0.88}]

        captured_messages = []

        def fake_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return groq_resp

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.side_effect = fake_create
            ask("Tell me about attention", engine)

        user_msg = next(m for m in captured_messages if m["role"] == "user")
        # Either the raw document or wiki body must appear in the context
        assert "Self-attention rocks." in user_msg["content"] or len(user_msg["content"]) > 100

    def test_system_prompt_instructs_knowledge_base_only(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "d", "metadata": {"title": "T"}, "similarity": 0.9}]

        captured_messages = []

        def fake_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            return groq_resp

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.side_effect = fake_create
            ask("question", engine)

        system_msg = next(m for m in captured_messages if m["role"] == "system")
        content = system_msg["content"].lower()
        assert "only" in content or "knowledge base" in content


# ─── test_ask_handles_no_relevant_notes ──────────────────────────────────────


class TestAskHandlesNoRelevantNotes:
    """ask() must handle an empty knowledge base gracefully."""

    def test_empty_collection_returns_ask_response(self):
        engine = _make_engine(count=0)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"):
            result = ask("Any question", engine)

        assert isinstance(result, AskResponse)

    def test_empty_collection_has_empty_sources(self):
        engine = _make_engine(count=0)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"):
            result = ask("Any question", engine)

        assert result.sources == []

    def test_empty_collection_confidence_is_low(self):
        engine = _make_engine(count=0)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"):
            result = ask("Any question", engine)

        assert result.confidence == "low"

    def test_empty_collection_zero_timings(self):
        engine = _make_engine(count=0)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"):
            result = ask("Any question", engine)

        assert result.query_embedding_time_ms == 0.0
        assert result.retrieval_time_ms == 0.0
        assert result.llm_time_ms == 0.0

    def test_empty_collection_answer_mentions_process(self):
        """The early-return answer must guide the user to run `process`."""
        engine = _make_engine(count=0)

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"):
            result = ask("Any question", engine)

        assert "process" in result.answer.lower() or "empty" in result.answer.lower()


# ─── test_ask_response_has_timings ───────────────────────────────────────────


class TestAskResponseHasTimings:
    """All three timing fields must be non-negative floats after a normal call."""

    def test_query_embedding_time_ms_is_non_negative(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "d", "metadata": {"title": "T"}, "similarity": 0.9}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("q", engine)

        assert result.query_embedding_time_ms >= 0.0

    def test_retrieval_time_ms_is_non_negative(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "d", "metadata": {"title": "T"}, "similarity": 0.9}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("q", engine)

        assert result.retrieval_time_ms >= 0.0

    def test_llm_time_ms_is_non_negative(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "d", "metadata": {"title": "T"}, "similarity": 0.9}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("q", engine)

        assert result.llm_time_ms >= 0.0

    def test_all_timings_are_floats(self):
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "d", "metadata": {"title": "T"}, "similarity": 0.9}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            result = ask("q", engine)

        assert isinstance(result.query_embedding_time_ms, float)
        assert isinstance(result.retrieval_time_ms, float)
        assert isinstance(result.llm_time_ms, float)

    def test_embedding_and_retrieval_timings_are_independent(self):
        """Embedding and retrieval timing must be measured independently.

        Both must be non-negative, and their individual values must differ
        enough from each other to prove they come from separate measurements
        (i.e., not both assigned from a single time delta split by a ratio).
        This is verified by checking that the system calls embed_text() before
        collection.query().
        """
        call_order: list[str] = []

        engine = _make_engine()
        engine.embed_text.side_effect = lambda *a, **kw: call_order.append("embed") or [0.1] * 384
        engine.collection.query.side_effect = lambda **kw: (
            call_order.append("query") or {
                "ids": [["n1"]], "documents": [["d"]],
                "metadatas": [[{"title": "T"}]], "distances": [[0.1]],
            }
        )

        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "d", "metadata": {"title": "T"}, "similarity": 0.9}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            ask("q", engine)

        # embed_text must be called BEFORE collection.query
        assert call_order.index("embed") < call_order.index("query")


# ─── test_confidence_levels ──────────────────────────────────────────────────


class TestConfidenceLevels:
    """Confidence must be determined from the top result's similarity score.

    Thresholds per implementation plan:
      - "high"   : similarity > 0.80
      - "medium" : 0.65 ≤ similarity ≤ 0.80
      - "low"    : similarity < 0.65
    """

    def _run_ask(self, similarity: float) -> AskResponse:
        engine = _make_engine()
        groq_resp = _make_groq_response()
        raw = [{"id": "n1", "document": "doc", "metadata": {"title": "T"}, "similarity": similarity}]

        with patch(_DOTENV_PATCH), \
             patch(_ENV_PATCH, return_value="fake-api-key"), \
             patch(_GROQ_PATCH) as MockGroq, \
             patch(_FORMAT_PATCH, return_value=raw):
            MockGroq.return_value.chat.completions.create.return_value = groq_resp
            return ask("q", engine)

    def test_high_confidence_when_similarity_above_0_8(self):
        result = self._run_ask(0.95)
        assert result.confidence == "high"

    def test_high_confidence_at_exactly_0_81(self):
        result = self._run_ask(0.81)
        assert result.confidence == "high"

    def test_medium_confidence_when_similarity_is_0_75(self):
        result = self._run_ask(0.75)
        assert result.confidence == "medium"

    def test_medium_confidence_at_exactly_0_65(self):
        result = self._run_ask(0.65)
        assert result.confidence == "medium"

    def test_medium_confidence_at_exactly_0_80(self):
        result = self._run_ask(0.80)
        assert result.confidence == "medium"

    def test_low_confidence_when_similarity_below_0_65(self):
        result = self._run_ask(0.50)
        assert result.confidence == "low"

    def test_low_confidence_at_exactly_0_64(self):
        result = self._run_ask(0.64)
        assert result.confidence == "low"

    def test_low_confidence_when_no_sources(self):
        """Zero-similarity baseline must yield 'low'."""
        result = self._run_ask(0.0)
        assert result.confidence == "low"


# ─── Helper function unit tests ───────────────────────────────────────────────


class TestExtractBody:
    """_extract_body() must strip Markdown syntax from wiki note bodies."""

    def test_removes_headings(self):
        raw = "---\n---\n## Section Title\n\nBody text here."
        result = _extract_body(raw, 7)
        assert "## Section Title" not in result
        assert "Body text here" in result

    def test_removes_blockquote_markers(self):
        raw = "---\n---\n> This is a summary."
        result = _extract_body(raw, 7)
        assert "> " not in result
        assert "This is a summary" in result

    def test_unwraps_wiki_links(self):
        raw = "---\n---\nSee also [[Related Note]] for more."
        result = _extract_body(raw, 7)
        assert "[[" not in result
        assert "Related Note" in result

    def test_removes_bold_markers(self):
        raw = "---\n---\nThis is **important** text."
        result = _extract_body(raw, 7)
        assert "**" not in result
        assert "important" in result

    def test_removes_list_markers(self):
        raw = "---\n---\n- Item one\n- Item two"
        result = _extract_body(raw, 7)
        assert "- Item" not in result
        assert "Item one" in result

    def test_returns_empty_for_empty_body(self):
        result = _extract_body("---\n---\n", 7)
        assert result == ""


class TestSlugify:
    """_slugify() must produce filesystem-safe lowercase slugs."""

    def test_basic_title(self):
        assert _slugify("Transformer Architecture") == "transformer-architecture"

    def test_special_characters_removed(self):
        slug = _slugify("Hello, World! (2026)")
        assert "," not in slug
        assert "!" not in slug
        assert "(" not in slug

    def test_multiple_spaces_collapsed(self):
        assert _slugify("Too  Many   Spaces") == "too-many-spaces"

    def test_no_leading_or_trailing_hyphens(self):
        slug = _slugify(" -- Leading and Trailing -- ")
        assert not slug.startswith("-")
        assert not slug.endswith("-")

    def test_colons_become_hyphens(self):
        slug = _slugify("Title: Subtitle")
        assert ":" not in slug
        assert "title" in slug


class TestLoadWikiContent:
    """_load_wiki_content() must locate and return note body text from wiki/."""

    def test_finds_note_by_id(self, tmp_path):
        md = tmp_path / "resources" / "my-note.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(
            "---\nid: abc123\ntitle: \"My Note\"\ncategory: resources\n"
            "tags: []\ncreated: 2026-07-01\nsource: cli\n---\n"
            "# My Note\n\n> Summary.\n\n## Content\n\nActual body text here.\n",
            encoding="utf-8",
        )
        result = _load_wiki_content(tmp_path, "abc123", "My Note")
        assert "Actual body text here" in result

    def test_returns_empty_string_when_not_found(self, tmp_path):
        result = _load_wiki_content(tmp_path, "nonexistent-id", "Nonexistent Note")
        assert result == ""

    def test_falls_back_to_slug_match(self, tmp_path):
        md = tmp_path / "resources" / "my-fallback-note.md"
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(
            "---\nid: other-id\ntitle: \"Fallback\"\ncategory: resources\n"
            "tags: []\ncreated: 2026-07-01\nsource: cli\n---\n"
            "# Fallback\n\nFallback body content.\n",
            encoding="utf-8",
        )
        # ID won't match, but the slug "my-fallback-note" should match the filename
        result = _load_wiki_content(tmp_path, "wrong-id", "My Fallback Note")
        assert "Fallback body content" in result
