"""
Tests for secondself.classify — Step 2.6

Covers all four cases from the implementation plan:
  - test_classify_returns_valid_para_category()
  - test_classify_returns_tags()
  - test_classify_returns_summary()
  - test_classify_handles_empty_content()

Strategy
--------
All tests mock the Groq API client so no real network call or API key is
needed.  ``classify()`` is called through ``classify_capture()`` wherever
possible to also exercise the content-extraction layer.

The mock injects a realistic JSON response matching what Groq actually
returns, then asserts on the parsed ``ClassificationResult`` fields.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from secondself.classify import ClassificationResult, classify, classify_capture


# ─── Helpers ───────────────────────────────────────────────────────────────


def _mock_groq_response(payload: dict) -> MagicMock:
    """Build a mock Groq chat-completion response that returns *payload* as JSON."""
    message = MagicMock()
    message.content = json.dumps(payload)

    choice = MagicMock()
    choice.message = message

    response = MagicMock()
    response.choices = [choice]
    return response


def _make_groq_client(payload: dict) -> MagicMock:
    """Return a mock Groq client whose ``chat.completions.create`` returns *payload*."""
    client = MagicMock()
    client.chat.completions.create.return_value = _mock_groq_response(payload)
    return client


# ─── Standard classification payload ──────────────────────────────────────

_RESOURCES_PAYLOAD = {
    "category": "resources",
    "tags": ["machine-learning", "transformers", "nlp"],
    "summary": "Seminal paper introducing the transformer architecture.",
    "suggested_title": "Attention Is All You Need",
    "confidence": 0.95,
}

_PROJECTS_PAYLOAD = {
    "category": "projects",
    "tags": ["deadline", "sprint", "coding"],
    "summary": "Active project with a hard deadline next week.",
    "suggested_title": "Sprint Goal Q3",
    "confidence": 0.88,
}

_AREAS_PAYLOAD = {
    "category": "areas",
    "tags": ["health", "exercise"],
    "summary": "Ongoing responsibility to maintain physical fitness.",
    "suggested_title": "Fitness Routine",
    "confidence": 0.80,
}

_ARCHIVES_PAYLOAD = {
    "category": "archives",
    "tags": ["completed", "old"],
    "summary": "Finished project from last year.",
    "suggested_title": "Old Project Archive",
    "confidence": 0.75,
}


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture()
def patch_groq():
    """
    Fixture that patches ``Groq`` and ``os.getenv`` so tests can control the
    LLM response without a real API key or network call.

    Usage::

        def test_something(patch_groq):
            client_mock = patch_groq(_RESOURCES_PAYLOAD)
            result = classify("some content")
            assert result.category == "resources"
    """
    def _factory(payload: dict) -> MagicMock:
        client = _make_groq_client(payload)
        return client

    with (
        patch("secondself.classify.os.getenv", return_value="fake-api-key"),
        patch("secondself.classify.Groq") as MockGroq,
    ):
        def setup(payload: dict):
            MockGroq.return_value = _make_groq_client(payload)
            return MockGroq.return_value

        yield setup


# ─── test_classify_returns_valid_para_category ────────────────────────────


class TestClassifyReturnsValidParaCategory:
    """classify() must always return one of the four PARA categories."""

    def test_resources_category(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Attention is all you need paper notes")
        assert result.category == "resources"

    def test_projects_category(self, patch_groq):
        patch_groq(_PROJECTS_PAYLOAD)
        result = classify("Sprint planning for Q3 deadline")
        assert result.category == "projects"

    def test_areas_category(self, patch_groq):
        patch_groq(_AREAS_PAYLOAD)
        result = classify("Daily workout and fitness goals")
        assert result.category == "areas"

    def test_archives_category(self, patch_groq):
        patch_groq(_ARCHIVES_PAYLOAD)
        result = classify("Old finished project notes from last year")
        assert result.category == "archives"

    def test_invalid_category_falls_back_to_resources(self, patch_groq):
        """If the LLM returns an invalid category, it must default to 'resources'."""
        patch_groq({
            "category": "INVALID_JUNK",
            "tags": [],
            "summary": "Something",
            "suggested_title": "Something",
            "confidence": 0.5,
        })
        result = classify("Some note content")
        assert result.category == "resources"

    def test_category_is_lowercased(self, patch_groq):
        """Category must be lowercased even if the LLM returns uppercase."""
        patch_groq({
            "category": "RESOURCES",
            "tags": [],
            "summary": "Upper case category test",
            "suggested_title": "Test",
            "confidence": 0.9,
        })
        result = classify("Some content")
        assert result.category == "resources"

    def test_returns_classification_result_type(self, patch_groq):
        """Return type must be ClassificationResult."""
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Any content")
        assert isinstance(result, ClassificationResult)

    def test_confidence_is_float(self, patch_groq):
        """confidence field must be a float between 0.0 and 1.0."""
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Some content")
        assert isinstance(result.confidence, float)
        assert 0.0 <= result.confidence <= 1.0


# ─── test_classify_returns_tags ───────────────────────────────────────────


class TestClassifyReturnsTags:
    """classify() must return a list of tags (up to 5)."""

    def test_tags_is_a_list(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Machine learning content")
        assert isinstance(result.tags, list)

    def test_tags_content_matches_response(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Transformer paper")
        assert "machine-learning" in result.tags
        assert "transformers" in result.tags
        assert "nlp" in result.tags

    def test_tags_capped_at_five(self, patch_groq):
        """Even if the LLM returns more than 5 tags, only 5 must be kept."""
        patch_groq({
            "category": "resources",
            "tags": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"],
            "summary": "Test",
            "suggested_title": "Test",
            "confidence": 0.9,
        })
        result = classify("Some content")
        assert len(result.tags) <= 5

    def test_tags_empty_when_llm_returns_none(self, patch_groq):
        """If the LLM returns no tags, result.tags must be an empty list."""
        patch_groq({
            "category": "resources",
            "tags": [],
            "summary": "No tags here",
            "suggested_title": "No Tags",
            "confidence": 0.8,
        })
        result = classify("Content with no tags")
        assert result.tags == []

    def test_non_list_tags_coerced_to_empty(self, patch_groq):
        """If the LLM returns tags as a non-list (e.g. a string), result must
        safely fall back to an empty list."""
        patch_groq({
            "category": "resources",
            "tags": "not-a-list",
            "summary": "Bad tags format",
            "suggested_title": "Bad Tags",
            "confidence": 0.7,
        })
        result = classify("Content")
        assert isinstance(result.tags, list)
        assert result.tags == []


# ─── test_classify_returns_summary ───────────────────────────────────────


class TestClassifyReturnsSummary:
    """classify() must return a non-empty summary string."""

    def test_summary_is_string(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Some content")
        assert isinstance(result.summary, str)

    def test_summary_matches_response(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Attention is all you need paper")
        assert result.summary == "Seminal paper introducing the transformer architecture."

    def test_suggested_title_is_string(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Transformer paper")
        assert isinstance(result.suggested_title, str)

    def test_suggested_title_matches_response(self, patch_groq):
        patch_groq(_RESOURCES_PAYLOAD)
        result = classify("Transformer content")
        assert result.suggested_title == "Attention Is All You Need"

    def test_summary_empty_string_on_missing_key(self, patch_groq):
        """If the LLM response omits 'summary', the field must default to ''."""
        patch_groq({
            "category": "resources",
            "tags": ["ai"],
            # deliberately no "summary" key
            "suggested_title": "No Summary",
            "confidence": 0.8,
        })
        result = classify("Content without summary")
        assert result.summary == ""


# ─── test_classify_handles_empty_content ─────────────────────────────────


class TestClassifyHandlesEmptyContent:
    """classify_capture() must handle empty/minimal captures without crashing."""

    def test_empty_note_content_is_handled(self, patch_groq):
        """classify_capture must not raise for a note with empty text."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "empty-note",
            "type": "note",
            "content": {"text": ""},
            "metadata": {},
        }
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)

    def test_missing_content_key_is_handled(self, patch_groq):
        """classify_capture must not raise when 'content' key is absent."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "no-content",
            "type": "note",
            "metadata": {},
        }
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)

    def test_url_capture_is_handled(self, patch_groq):
        """URL captures must extract url + text and pass them to classify."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "url-cap",
            "type": "url",
            "content": {
                "url": "https://arxiv.org/abs/1706.03762",
                "text": "Attention Is All You Need abstract text",
            },
            "metadata": {"title": "Attention Paper"},
        }
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)
        assert result.category in ("projects", "areas", "resources", "archives")

    def test_file_capture_is_handled(self, patch_groq):
        """File captures must use file_content for classification."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "file-cap",
            "type": "file",
            "content": {
                "file_path": "/path/to/paper.pdf",
                "file_content": "Extracted text from the PDF document.",
            },
            "metadata": {},
        }
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)

    def test_file_capture_without_content_uses_path(self, patch_groq):
        """If file_content is empty, classify_capture must use file_path as fallback."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "binary-cap",
            "type": "file",
            "content": {
                "file_path": "/path/to/image.png",
                "file_content": "",
            },
            "metadata": {},
        }
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)

    def test_unknown_type_is_handled(self, patch_groq):
        """An unknown capture type must not raise — content dict is stringified."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "weird-cap",
            "type": "video",
            "content": {"some_key": "some_value"},
            "metadata": {},
        }
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)

    def test_whitespace_only_content_sent_as_empty_content(self, patch_groq):
        """Whitespace-only text must be treated as 'Empty content' (no API crash)."""
        patch_groq(_RESOURCES_PAYLOAD)
        capture = {
            "id": "whitespace-cap",
            "type": "note",
            "content": {"text": "   \n\t  "},
            "metadata": {},
        }
        # Should not raise — classify is called with "Empty content"
        result = classify_capture(capture)
        assert isinstance(result, ClassificationResult)


# ─── API error handling ───────────────────────────────────────────────────


class TestClassifyApiErrorHandling:
    """classify() must retry once and then raise on persistent API failures."""

    def test_retries_once_on_failure(self):
        """On the first call failing, classify() should retry exactly once."""
        call_count = 0

        def flaky_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Temporary API error")
            return _mock_groq_response(_RESOURCES_PAYLOAD)

        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = flaky_create

        with (
            patch("secondself.classify.os.getenv", return_value="fake-key"),
            patch("secondself.classify.Groq", return_value=mock_client),
            patch("secondself.classify.time.sleep"),  # skip real sleep
        ):
            result = classify("Some content")

        assert call_count == 2  # one failure + one success
        assert result.category == "resources"

    def test_raises_after_all_retries_exhausted(self):
        """If the API fails on every attempt, classify() must raise."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = RuntimeError("Persistent API error")

        with (
            patch("secondself.classify.os.getenv", return_value="fake-key"),
            patch("secondself.classify.Groq", return_value=mock_client),
            patch("secondself.classify.time.sleep"),
        ):
            with pytest.raises(RuntimeError, match="Persistent API error"):
                classify("Some content")

    def test_raises_when_no_api_key(self):
        """classify() must raise ValueError immediately if GROQ_API_KEY is missing."""
        with patch("secondself.classify.os.getenv", return_value=None):
            with pytest.raises(ValueError, match="GROQ_API_KEY"):
                classify("Some content")
