"""
Tests for secondself.wiki_writer — Step 2.4

Covers:
  - slugify()          edge cases and unicode handling
  - write_wiki_note()  frontmatter fields, body structure, conflict resolution,
                       related-notes links, idempotent re-processing
  - private helpers    _resolve_title, _resolve_source, _extract_content_text
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from secondself.classify import ClassificationResult
from secondself.wiki_writer import (
    _build_body,
    _escape_yaml_string,
    _extract_content_text,
    _find_existing_by_id,
    _format_tags_yaml,
    _resolve_source,
    _resolve_title,
    slugify,
    write_wiki_note,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────


def _make_classification(
    category: str = "resources",
    tags: list[str] | None = None,
    summary: str = "A one-line summary.",
    suggested_title: str = "Test Note Title",
    confidence: float = 0.92,
) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        tags=tags if tags is not None else ["ai", "testing"],
        summary=summary,
        suggested_title=suggested_title,
        confidence=confidence,
    )


def _make_note_capture(
    capture_id: str = "aaaa-bbbb-cccc-dddd",
    text: str = "This is the note content.",
    title: str = "My Note",
) -> dict:
    return {
        "id": capture_id,
        "timestamp": "2026-07-15T10:00:00+05:30",
        "type": "note",
        "source": "cli",
        "content": {"text": text},
        "metadata": {"title": title, "word_count": 5, "char_count": 25},
    }


def _make_url_capture(
    capture_id: str = "url-1111-2222-3333",
    url: str = "https://example.com/article",
    text: str = "Example Article\n\nAn interesting article.",
    title: str = "Example Article",
) -> dict:
    return {
        "id": capture_id,
        "timestamp": "2026-07-16T12:00:00+05:30",
        "type": "url",
        "source": "cli",
        "content": {"url": url, "text": text},
        "metadata": {"title": title, "fetch_failed": False},
    }


def _make_file_capture(
    capture_id: str = "file-aaaa-bbbb-cccc",
    file_path: str = "/path/to/document.pdf",
    file_content: str = "Extracted PDF text here.",
) -> dict:
    return {
        "id": capture_id,
        "timestamp": "2026-07-17T08:00:00+05:30",
        "type": "file",
        "source": "cli",
        "content": {"file_path": file_path, "file_content": file_content},
        "metadata": {"title": "document.pdf"},
    }


# ─── slugify ───────────────────────────────────────────────────────────────


class TestSlugify:
    def test_basic(self):
        assert slugify("Hello World") == "hello-world"

    def test_strips_punctuation(self):
        assert slugify("Attention Is All You Need!") == "attention-is-all-you-need"

    def test_collapses_spaces(self):
        assert slugify("too   many   spaces") == "too-many-spaces"

    def test_converts_underscores(self):
        assert slugify("snake_case_title") == "snake-case-title"

    def test_already_slug(self):
        assert slugify("already-a-slug") == "already-a-slug"

    def test_colon_becomes_hyphen(self):
        # "PARA method: Projects" → "para-method-projects"
        result = slugify("PARA method: Projects, Areas")
        assert ":" not in result
        assert result.startswith("para-method")

    def test_empty_string(self):
        assert slugify("") == ""

    def test_strips_leading_trailing_hyphens(self):
        assert slugify("!!! Title !!!") == "title"

    def test_all_special_chars(self):
        result = slugify("@#$%^&*()")
        # Should reduce to empty or minimal output without crashing
        assert isinstance(result, str)

    def test_long_title(self):
        title = "A " * 50  # 100 chars
        result = slugify(title)
        assert "  " not in result
        assert result == result.lower()


# ─── _resolve_title ────────────────────────────────────────────────────────


class TestResolveTitle:
    def test_prefers_suggested_title(self):
        capture = _make_note_capture(title="Metadata Title")
        cls = _make_classification(suggested_title="LLM Title")
        assert _resolve_title(capture, cls) == "LLM Title"

    def test_falls_back_to_metadata_title_when_suggested_empty(self):
        capture = _make_note_capture(title="Metadata Title")
        cls = _make_classification(suggested_title="")
        assert _resolve_title(capture, cls) == "Metadata Title"

    def test_falls_back_to_content_text(self):
        capture = _make_note_capture(title="", text="Content first line\nmore content")
        cls = _make_classification(suggested_title="", summary="")
        # With empty metadata title, should take first line of content
        result = _resolve_title(capture, cls)
        assert "Content first line" in result

    def test_returns_untitled_as_last_resort(self):
        capture = {"id": "x", "type": "note", "content": {}, "metadata": {}}
        cls = _make_classification(suggested_title="")
        result = _resolve_title(capture, cls)
        assert result == "Untitled Note"


# ─── _resolve_source ───────────────────────────────────────────────────────


class TestResolveSource:
    def test_url_capture_returns_url(self):
        capture = _make_url_capture(url="https://arxiv.org/abs/1234")
        assert _resolve_source(capture) == "https://arxiv.org/abs/1234"

    def test_file_capture_returns_path(self):
        capture = _make_file_capture(file_path="/docs/paper.pdf")
        assert _resolve_source(capture) == "/docs/paper.pdf"

    def test_note_capture_returns_cli(self):
        capture = _make_note_capture()
        assert _resolve_source(capture) == "cli"


# ─── _extract_content_text ─────────────────────────────────────────────────


class TestExtractContentText:
    def test_note_returns_text(self):
        capture = _make_note_capture(text="Hello world")
        assert _extract_content_text(capture) == "Hello world"

    def test_url_prepends_url(self):
        capture = _make_url_capture(url="https://example.com", text="Article body")
        result = _extract_content_text(capture)
        assert "https://example.com" in result
        assert "Article body" in result

    def test_file_returns_file_content(self):
        capture = _make_file_capture(file_content="PDF text")
        assert _extract_content_text(capture) == "PDF text"

    def test_file_falls_back_to_path(self):
        capture = _make_file_capture(file_content="", file_path="/path/to/file.pdf")
        result = _extract_content_text(capture)
        assert "/path/to/file.pdf" in result


# ─── _format_tags_yaml ─────────────────────────────────────────────────────


class TestFormatTagsYaml:
    def test_empty_tags(self):
        assert _format_tags_yaml([]) == "[]"

    def test_single_tag(self):
        assert _format_tags_yaml(["ai"]) == '["ai"]'

    def test_multiple_tags(self):
        result = _format_tags_yaml(["ai", "nlp", "transformers"])
        assert result == '["ai", "nlp", "transformers"]'


# ─── _escape_yaml_string ───────────────────────────────────────────────────


class TestEscapeYamlString:
    def test_no_quotes(self):
        assert _escape_yaml_string("Hello World") == "Hello World"

    def test_escapes_double_quotes(self):
        assert _escape_yaml_string('Say "hello"') == 'Say \\"hello\\"'


# ─── write_wiki_note ───────────────────────────────────────────────────────


class TestWriteWikiNote:
    """Integration-level tests using a temporary WIKI_DIR."""

    def _patch_wiki_dir(self, monkeypatch, tmp_path: Path):
        """Redirect WIKI_DIR to tmp_path inside wiki_writer module."""
        import secondself.wiki_writer as ww_module
        monkeypatch.setattr(ww_module, "WIKI_DIR", tmp_path)
        # Create PARA sub-dirs
        for cat in ("projects", "areas", "resources", "archives"):
            (tmp_path / cat).mkdir(parents=True, exist_ok=True)

    # ── Frontmatter ──────────────────────────────────────────────────────

    def test_creates_file_in_correct_category(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(category="resources")

        path = write_wiki_note(capture, cls, related=[])

        assert path.parent == tmp_path / "resources"
        assert path.suffix == ".md"

    def test_frontmatter_contains_id(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture(capture_id="test-uuid-1234")
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "id: test-uuid-1234" in content

    def test_frontmatter_contains_category(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(category="projects")

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "category: projects" in content

    def test_frontmatter_contains_tags(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(tags=["machine-learning", "nlp"])

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "machine-learning" in content
        assert "nlp" in content

    def test_frontmatter_contains_timestamp(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "created: 2026-07-15" in content

    def test_frontmatter_contains_confidence(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(confidence=0.87)

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "confidence: 0.87" in content

    # ── Body structure ───────────────────────────────────────────────────

    def test_body_has_h1_heading(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(suggested_title="My Great Note")

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "# My Great Note" in content

    def test_body_has_summary(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(summary="This is the AI summary.")

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "This is the AI summary." in content

    def test_body_has_original_content(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture(text="Original note text from user.")
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "Original note text from user." in content

    def test_body_has_related_notes_section(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification()
        related = [
            {"id": "r1", "title": "Related A", "similarity": 0.9},
            {"id": "r2", "title": "Related B", "similarity": 0.75},
        ]

        path = write_wiki_note(capture, cls, related=related)
        content = path.read_text(encoding="utf-8")

        assert "## Related Notes" in content
        assert "[[Related A]]" in content
        assert "[[Related B]]" in content

    def test_body_has_empty_related_notes_section_when_none(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        # Section header must always be present (for future backlinks)
        assert "## Related Notes" in content

    # ── Slug / filename ──────────────────────────────────────────────────

    def test_filename_is_slugified_title(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification(suggested_title="Attention Is All You Need")

        path = write_wiki_note(capture, cls, related=[])

        assert path.stem == "attention-is-all-you-need"

    def test_conflict_resolution_appends_counter(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        # Pre-create a file at the expected slug location
        (tmp_path / "resources" / "my-note.md").write_text("existing", encoding="utf-8")

        # Write a *different* capture that generates the same slug
        capture = _make_note_capture(capture_id="new-uuid-9999")
        cls = _make_classification(suggested_title="My Note")

        path = write_wiki_note(capture, cls, related=[])

        assert path.stem == "my-note-2"

    # ── Idempotent re-processing ─────────────────────────────────────────

    def test_reprocessing_overwrites_same_file(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture(capture_id="stable-uuid-0001")
        cls = _make_classification(suggested_title="Stable Title")

        path1 = write_wiki_note(capture, cls, related=[])

        # Re-process with updated summary
        cls2 = _make_classification(
            suggested_title="Stable Title", summary="Updated summary."
        )
        path2 = write_wiki_note(capture, cls2, related=[])

        assert path1 == path2  # Same file, not a new one
        assert "Updated summary." in path2.read_text(encoding="utf-8")

    def test_no_extra_files_on_reprocess(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture(capture_id="stable-uuid-0002")
        cls = _make_classification()

        write_wiki_note(capture, cls, related=[])
        write_wiki_note(capture, cls, related=[])

        md_files = list((tmp_path / "resources").glob("*.md"))
        assert len(md_files) == 1

    # ── Capture types ────────────────────────────────────────────────────

    def test_url_capture_includes_url_in_content(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_url_capture(url="https://arxiv.org/abs/1706.03762")
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "arxiv.org" in content

    def test_file_capture_includes_file_content(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_file_capture(file_content="Extracted PDF text goes here.")
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        assert "Extracted PDF text goes here." in content

    # ── Valid markdown ───────────────────────────────────────────────────

    def test_frontmatter_is_valid_yaml_delimited(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification()

        path = write_wiki_note(capture, cls, related=[])
        content = path.read_text(encoding="utf-8")

        # Must start with --- and have a closing ---
        assert content.startswith("---\n")
        parts = content.split("---\n", 2)
        assert len(parts) >= 3  # ["", frontmatter, body]

    def test_returns_path_object(self, tmp_path, monkeypatch):
        self._patch_wiki_dir(monkeypatch, tmp_path)
        capture = _make_note_capture()
        cls = _make_classification()

        result = write_wiki_note(capture, cls, related=[])

        assert isinstance(result, Path)
        assert result.exists()


# ─── _find_existing_by_id ──────────────────────────────────────────────────


class TestFindExistingById:
    def test_finds_file_with_matching_id(self, tmp_path):
        note = tmp_path / "some-note.md"
        note.write_text(
            "---\nid: my-capture-id\ntitle: \"Test\"\n---\n\n# Test\n",
            encoding="utf-8",
        )

        result = _find_existing_by_id(tmp_path, "my-capture-id")
        assert result == note

    def test_returns_none_when_no_match(self, tmp_path):
        note = tmp_path / "other.md"
        note.write_text("---\nid: other-id\ntitle: \"Other\"\n---\n\n# Other\n", encoding="utf-8")

        result = _find_existing_by_id(tmp_path, "nonexistent-id")
        assert result is None

    def test_returns_none_for_empty_directory(self, tmp_path):
        result = _find_existing_by_id(tmp_path, "any-id")
        assert result is None
