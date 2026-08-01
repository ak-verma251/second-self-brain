"""
Tests for secondself.linker — Step 2.3

Covers:
  - find_related()      respects threshold and caps at MAX_LINKS_PER_NOTE
  - insert_links()      creates the Related Notes section; is idempotent
  - update_backlinks()  inserts reciprocal links; is idempotent
  - _find_wiki_file_by_title() (indirectly via update_backlinks)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from secondself.linker import (
    _find_wiki_file_by_title,
    _slugify,
    find_related,
    insert_links,
    update_backlinks,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────


def _make_engine(results: list[dict]) -> MagicMock:
    """Return a mock EmbeddingEngine whose query_similar_by_id returns *results*."""
    engine = MagicMock()
    engine.query_similar_by_id.return_value = results
    return engine


def _make_result(
    id_: str,
    title: str = "",
    similarity: float = 0.9,
) -> dict:
    """Build a raw query result dict as returned by EmbeddingEngine."""
    return {
        "id": id_,
        "document": "some content",
        "metadata": {"title": title},
        "similarity": similarity,
    }


def _write_note(directory: Path, filename: str, title: str, body: str = "") -> Path:
    """Write a minimal wiki note with YAML frontmatter."""
    path = directory / filename
    content = (
        f"---\n"
        f"title: {title}\n"
        f"category: resources\n"
        f"---\n\n"
        f"# {title}\n\n"
        f"{body}"
    )
    path.write_text(content, encoding="utf-8")
    return path


# ─── find_related ──────────────────────────────────────────────────────────


class TestFindRelated:
    def test_returns_results_above_threshold(self):
        """Notes with similarity >= SIMILARITY_THRESHOLD must be included."""
        results = [
            _make_result("abc", "Note A", similarity=0.85),
            _make_result("def", "Note B", similarity=0.70),
        ]
        engine = _make_engine(results)

        related = find_related("source-id", engine)

        assert len(related) == 2
        assert related[0]["id"] == "abc"
        assert related[0]["title"] == "Note A"
        assert related[0]["similarity"] == 0.85

    def test_respects_similarity_threshold(self, monkeypatch):
        """Notes below SIMILARITY_THRESHOLD (0.65) must be excluded."""
        from secondself import linker as linker_module

        monkeypatch.setattr(linker_module, "SIMILARITY_THRESHOLD", 0.65)

        results = [
            _make_result("abc", "Note A", similarity=0.80),
            _make_result("def", "Note B", similarity=0.60),  # below threshold
            _make_result("ghi", "Note C", similarity=0.30),  # well below
        ]
        engine = _make_engine(results)

        related = find_related("source-id", engine)

        ids = [r["id"] for r in related]
        assert "abc" in ids
        assert "def" not in ids
        assert "ghi" not in ids

    def test_caps_at_max_links_per_note(self, monkeypatch):
        """Result list must never exceed MAX_LINKS_PER_NOTE."""
        from secondself import linker as linker_module

        monkeypatch.setattr(linker_module, "MAX_LINKS_PER_NOTE", 3)

        results = [
            _make_result(str(i), f"Note {i}", similarity=0.90)
            for i in range(10)
        ]
        engine = _make_engine(results)

        related = find_related("source-id", engine)

        assert len(related) <= 3

    def test_excludes_self_match(self):
        """The source note itself must never appear in the results."""
        results = [
            _make_result("source-id", "Self", similarity=1.0),  # self
            _make_result("other-id", "Other", similarity=0.80),
        ]
        engine = _make_engine(results)

        related = find_related("source-id", engine)

        ids = [r["id"] for r in related]
        assert "source-id" not in ids
        assert "other-id" in ids

    def test_empty_collection_returns_empty(self):
        """An empty result set from the engine should yield an empty list."""
        engine = _make_engine([])
        related = find_related("source-id", engine)
        assert related == []

    def test_uses_id_prefix_as_title_fallback(self):
        """If metadata has no title, the first 8 chars of the ID are used."""
        results = [_make_result("abcdefgh1234", title="", similarity=0.80)]
        engine = _make_engine(results)

        related = find_related("source-id", engine)

        assert related[0]["title"] == "abcdefgh"  # first 8 chars


# ─── insert_links ──────────────────────────────────────────────────────────


class TestInsertLinks:
    def test_creates_related_notes_section(self, tmp_path):
        """If no Related Notes section exists, it must be created."""
        note = tmp_path / "note.md"
        note.write_text("# My Note\n\nSome content.\n", encoding="utf-8")

        related = [{"id": "abc", "title": "Linked Note", "similarity": 0.9}]
        insert_links(note, related)

        content = note.read_text(encoding="utf-8")
        assert "## Related Notes" in content
        assert "[[Linked Note]]" in content

    def test_appends_to_existing_section(self, tmp_path):
        """Links must be added inside an existing Related Notes section."""
        note = tmp_path / "note.md"
        note.write_text(
            "# My Note\n\n## Related Notes\n- [[Existing Note]]\n",
            encoding="utf-8",
        )

        related = [{"id": "xyz", "title": "New Note", "similarity": 0.75}]
        insert_links(note, related)

        content = note.read_text(encoding="utf-8")
        assert "[[Existing Note]]" in content
        assert "[[New Note]]" in content

    def test_is_idempotent(self, tmp_path):
        """Calling insert_links twice must not create duplicate links."""
        note = tmp_path / "note.md"
        note.write_text("# My Note\n\nContent.\n", encoding="utf-8")

        related = [{"id": "abc", "title": "Alpha", "similarity": 0.9}]

        insert_links(note, related)
        insert_links(note, related)

        content = note.read_text(encoding="utf-8")
        assert content.count("[[Alpha]]") == 1

    def test_does_nothing_for_empty_related(self, tmp_path):
        """No changes should occur when the related list is empty."""
        note = tmp_path / "note.md"
        original = "# My Note\n\nContent.\n"
        note.write_text(original, encoding="utf-8")

        insert_links(note, [])

        assert note.read_text(encoding="utf-8") == original

    def test_does_nothing_for_nonexistent_file(self, tmp_path):
        """Missing file should be silently skipped (no exception)."""
        missing = tmp_path / "ghost.md"
        insert_links(missing, [{"id": "x", "title": "Y", "similarity": 0.9}])
        assert not missing.exists()

    def test_respects_max_links_cap(self, tmp_path, monkeypatch):
        """At most MAX_LINKS_PER_NOTE links must be written."""
        from secondself import linker as linker_module

        monkeypatch.setattr(linker_module, "MAX_LINKS_PER_NOTE", 2)

        note = tmp_path / "note.md"
        note.write_text("# Note\n", encoding="utf-8")

        related = [
            {"id": str(i), "title": f"Note {i}", "similarity": 0.9}
            for i in range(5)
        ]
        insert_links(note, related)

        content = note.read_text(encoding="utf-8")
        link_count = content.count("[[")
        assert link_count <= 2


# ─── update_backlinks ──────────────────────────────────────────────────────


class TestUpdateBacklinks:
    def test_adds_backlink_to_related_note(self, tmp_path):
        """The source title must appear as [[link]] in each related note."""
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()

        target = _write_note(resources_dir, "related-note.md", "Related Note")
        related = [{"id": "r1", "title": "Related Note", "similarity": 0.88}]

        update_backlinks(tmp_path, "Source Note", related)

        content = target.read_text(encoding="utf-8")
        assert "[[Source Note]]" in content

    def test_is_idempotent(self, tmp_path):
        """Running update_backlinks twice must not duplicate backlinks."""
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()

        target = _write_note(resources_dir, "alpha.md", "Alpha")
        related = [{"id": "a1", "title": "Alpha", "similarity": 0.80}]

        update_backlinks(tmp_path, "Source", related)
        update_backlinks(tmp_path, "Source", related)

        content = target.read_text(encoding="utf-8")
        assert content.count("[[Source]]") == 1

    def test_skips_missing_wiki_file(self, tmp_path):
        """If a related note's file doesn't exist, no error should be raised."""
        related = [{"id": "ghost", "title": "Ghost Note", "similarity": 0.9}]
        # Should complete without exception even though the file doesn't exist.
        update_backlinks(tmp_path, "Source", related)

    def test_creates_related_section_if_absent(self, tmp_path):
        """Backlink should add the Related Notes section if it is missing."""
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()

        target = _write_note(resources_dir, "bare.md", "Bare Note", body="")
        # Remove any pre-existing Related Notes section to be safe
        original = target.read_text(encoding="utf-8")
        assert "## Related Notes" not in original

        related = [{"id": "b1", "title": "Bare Note", "similarity": 0.75}]
        update_backlinks(tmp_path, "Source", related)

        content = target.read_text(encoding="utf-8")
        assert "## Related Notes" in content
        assert "[[Source]]" in content


# ─── _slugify helper ───────────────────────────────────────────────────────


class TestSlugify:
    def test_basic_slugification(self):
        assert _slugify("Hello World") == "hello-world"

    def test_strips_special_characters(self):
        assert _slugify("Attention Is All You Need!") == "attention-is-all-you-need"

    def test_handles_multiple_spaces(self):
        assert _slugify("too   many   spaces") == "too-many-spaces"

    def test_handles_underscores(self):
        assert _slugify("snake_case_title") == "snake-case-title"

    def test_already_slug(self):
        assert _slugify("already-a-slug") == "already-a-slug"


# ─── _find_wiki_file_by_title (unit) ───────────────────────────────────────


class TestFindWikiFileByTitle:
    def test_finds_by_frontmatter_title(self, tmp_path):
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()
        _write_note(resources_dir, "some-note.md", "My Important Note")

        result = _find_wiki_file_by_title(tmp_path, "My Important Note")
        assert result is not None
        assert result.name == "some-note.md"

    def test_case_insensitive_match(self, tmp_path):
        resources_dir = tmp_path / "resources"
        resources_dir.mkdir()
        _write_note(resources_dir, "note.md", "My Note")

        result = _find_wiki_file_by_title(tmp_path, "my note")
        assert result is not None

    def test_returns_none_when_not_found(self, tmp_path):
        result = _find_wiki_file_by_title(tmp_path, "Nonexistent Title")
        assert result is None

    def test_slug_fallback_match(self, tmp_path):
        """Should find a file by slug when frontmatter title doesn't match."""
        area_dir = tmp_path / "areas"
        area_dir.mkdir()
        # File with no frontmatter — just a plain heading
        bare = area_dir / "machine-learning.md"
        bare.write_text("# Machine Learning\n\nContent.\n", encoding="utf-8")

        result = _find_wiki_file_by_title(tmp_path, "Machine Learning")
        assert result is not None
        assert result.name == "machine-learning.md"
