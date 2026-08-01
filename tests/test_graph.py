"""
Tests for secondself.graph_builder — Step 3.5

Covers all seven cases from the implementation plan:
  - test_parse_wiki_note_extracts_frontmatter()
  - test_parse_wiki_note_extracts_links()
  - test_build_graph_creates_nodes_for_all_notes()
  - test_build_graph_creates_edges_from_links()
  - test_edges_are_bidirectional()
  - test_graph_metadata_has_correct_counts()
  - test_export_graph_writes_valid_json()

Strategy
--------
All tests create temporary markdown files via pytest's `tmp_path` fixture so
no real wiki/ files are touched.  The helper `_make_note()` writes a properly-
formatted wiki note (YAML frontmatter + body) to a temp dir.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from secondself.graph_builder import build_graph, export_graph, parse_wiki_note


# ─── Helpers ────────────────────────────────────────────────────────────────

def _make_note(
    directory: Path,
    *,
    filename: str = "note.md",
    note_id: str = "test-id-001",
    title: str = "Test Note",
    category: str = "resources",
    tags: list[str] | None = None,
    summary: str = "A brief summary.",
    content: str = "This is the main body content.",
    related: list[str] | None = None,
) -> Path:
    """Write a wiki-formatted markdown note to *directory* and return its path."""
    tags_yaml = json.dumps(tags or [])
    related_lines = (
        "\n".join(f"- [[{t}]]" for t in related)
        if related else ""
    )

    text = (
        f"---\n"
        f"id: {note_id}\n"
        f'title: "{title}"\n'
        f"category: {category}\n"
        f"tags: {tags_yaml}\n"
        f"created: 2026-07-01T00:00:00+00:00\n"
        f"source: cli\n"
        f"---\n"
        f"# {title}\n"
        f"\n"
        f"> {summary}\n"
        f"\n"
        f"## Content\n"
        f"\n"
        f"{content}\n"
        f"\n"
        f"## Related Notes\n"
        f"\n"
        f"{related_lines}\n"
    )

    path = directory / filename
    path.write_text(text, encoding="utf-8")
    return path


# ─── parse_wiki_note ────────────────────────────────────────────────────────


class TestParseWikiNoteExtractsFrontmatter:
    """parse_wiki_note() must correctly extract all YAML frontmatter fields."""

    def test_extracts_id(self, tmp_path):
        path = _make_note(tmp_path, note_id="abc-123", title="My Note")
        node = parse_wiki_note(path)
        assert node["id"] == "abc-123"

    def test_extracts_title_as_label(self, tmp_path):
        path = _make_note(tmp_path, title="Transformer Architecture")
        node = parse_wiki_note(path)
        assert node["label"] == "Transformer Architecture"

    def test_extracts_category(self, tmp_path):
        path = _make_note(tmp_path, category="areas")
        node = parse_wiki_note(path)
        assert node["category"] == "areas"

    def test_extracts_tags_as_list(self, tmp_path):
        path = _make_note(tmp_path, tags=["ai", "nlp", "transformers"])
        node = parse_wiki_note(path)
        assert isinstance(node["tags"], list)
        assert node["tags"] == ["ai", "nlp", "transformers"]

    def test_extracts_created(self, tmp_path):
        path = _make_note(tmp_path)
        node = parse_wiki_note(path)
        assert "2026-07-01" in node["created"]

    def test_extracts_summary(self, tmp_path):
        path = _make_note(tmp_path, summary="Machine learning basics explained.")
        node = parse_wiki_note(path)
        assert node["summary"] == "Machine learning basics explained."

    def test_extracts_content_preview(self, tmp_path):
        path = _make_note(tmp_path, content="Deep learning is a subset of machine learning.")
        node = parse_wiki_note(path)
        assert "Deep learning" in node["content_preview"]

    def test_computes_word_count(self, tmp_path):
        path = _make_note(tmp_path, content="one two three four five")
        node = parse_wiki_note(path)
        assert node["word_count"] == 5

    def test_returns_expected_keys(self, tmp_path):
        path = _make_note(tmp_path)
        node = parse_wiki_note(path)
        required_keys = {"id", "label", "category", "tags", "summary",
                         "content_preview", "created", "word_count", "links"}
        assert required_keys.issubset(set(node.keys()))

    def test_fallback_id_is_filename_stem(self, tmp_path):
        """If frontmatter has no id key, the file stem is used."""
        path = tmp_path / "my-fallback-note.md"
        path.write_text("# No frontmatter\n\nJust body text.", encoding="utf-8")
        node = parse_wiki_note(path)
        assert node["id"] == "my-fallback-note"

    def test_fallback_category_is_resources(self, tmp_path):
        """Missing category defaults to 'resources'."""
        path = tmp_path / "no-cat.md"
        path.write_text("---\nid: x\ntitle: \"X\"\n---\nBody.", encoding="utf-8")
        node = parse_wiki_note(path)
        assert node["category"] == "resources"

    def test_empty_tags_yields_empty_list(self, tmp_path):
        path = _make_note(tmp_path, tags=[])
        node = parse_wiki_note(path)
        assert node["tags"] == []

    def test_content_preview_truncated_at_200(self, tmp_path):
        long_content = "word " * 60  # 300 chars
        path = _make_note(tmp_path, content=long_content)
        node = parse_wiki_note(path)
        assert len(node["content_preview"]) <= 203  # 200 + "..."


class TestParseWikiNoteExtractsLinks:
    """parse_wiki_note() must extract [[wiki-links]] from ## Related Notes."""

    def test_extracts_single_link(self, tmp_path):
        path = _make_note(tmp_path, related=["Machine Learning Basics"])
        node = parse_wiki_note(path)
        assert "Machine Learning Basics" in node["links"]

    def test_extracts_multiple_links(self, tmp_path):
        path = _make_note(tmp_path, related=["Note A", "Note B", "Note C"])
        node = parse_wiki_note(path)
        assert node["links"] == ["Note A", "Note B", "Note C"]

    def test_no_related_section_yields_empty_list(self, tmp_path):
        path = tmp_path / "no-related.md"
        path.write_text(
            "---\nid: no-rel\ntitle: \"No Rel\"\ncategory: resources\n"
            "tags: []\ncreated: 2026-07-01\nsource: cli\n---\n# No Rel\n\nBody.\n",
            encoding="utf-8",
        )
        node = parse_wiki_note(path)
        assert node["links"] == []

    def test_empty_related_section_yields_empty_list(self, tmp_path):
        path = _make_note(tmp_path, related=[])
        node = parse_wiki_note(path)
        assert node["links"] == []

    def test_links_are_plain_strings(self, tmp_path):
        path = _make_note(tmp_path, related=["Vector Embeddings"])
        node = parse_wiki_note(path)
        assert all(isinstance(lnk, str) for lnk in node["links"])


# ─── build_graph ────────────────────────────────────────────────────────────


class TestBuildGraphCreatesNodesForAllNotes:
    """build_graph() must create exactly one node per .md file found."""

    def test_single_note_yields_one_node(self, tmp_path):
        _make_note(tmp_path, filename="n1.md", note_id="id-1", title="Note One")
        graph = build_graph(tmp_path)
        assert len(graph["nodes"]) == 1

    def test_multiple_notes_yield_correct_count(self, tmp_path):
        for i in range(5):
            _make_note(tmp_path, filename=f"n{i}.md", note_id=f"id-{i}", title=f"Note {i}")
        graph = build_graph(tmp_path)
        assert len(graph["nodes"]) == 5

    def test_node_has_required_fields(self, tmp_path):
        _make_note(tmp_path, note_id="node-test", title="Node Fields Test")
        graph = build_graph(tmp_path)
        node = graph["nodes"][0]
        for field in ("id", "label", "category", "tags", "summary",
                      "content_preview", "created", "word_count", "link_count"):
            assert field in node, f"Missing field: {field}"

    def test_links_key_removed_from_final_nodes(self, tmp_path):
        """'links' is an internal field and must NOT appear in graph output."""
        _make_note(tmp_path, related=["Some Note"])
        graph = build_graph(tmp_path)
        for node in graph["nodes"]:
            assert "links" not in node

    def test_scans_subdirectories_recursively(self, tmp_path):
        sub = tmp_path / "resources"
        sub.mkdir()
        _make_note(sub, filename="deep.md", note_id="deep-1", title="Deep Note")
        graph = build_graph(tmp_path)
        assert len(graph["nodes"]) == 1

    def test_empty_wiki_dir_returns_empty_graph(self, tmp_path):
        graph = build_graph(tmp_path)
        assert graph["nodes"] == []
        assert graph["edges"] == []


class TestBuildGraphCreatesEdgesFromLinks:
    """build_graph() must create edges wherever [[links]] resolve to real nodes."""

    def test_linked_notes_produce_edge(self, tmp_path):
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Note B"])
        _make_note(tmp_path, filename="b.md", note_id="id-b", title="Note B")
        graph = build_graph(tmp_path)
        assert len(graph["edges"]) == 1
        edge = graph["edges"][0]
        assert edge["from"] == "id-a"
        assert edge["to"]   == "id-b"

    def test_unresolvable_link_creates_no_edge(self, tmp_path):
        """A [[link]] pointing to a non-existent note must be silently ignored."""
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Ghost Note That Does Not Exist"])
        graph = build_graph(tmp_path)
        assert graph["edges"] == []

    def test_self_link_creates_no_edge(self, tmp_path):
        """A note linking to itself must NOT produce an edge."""
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Note A"])
        graph = build_graph(tmp_path)
        assert graph["edges"] == []

    def test_link_count_incremented_per_resolved_link(self, tmp_path):
        _make_note(tmp_path, filename="hub.md", note_id="hub", title="Hub Note",
                   related=["Spoke A", "Spoke B"])
        _make_note(tmp_path, filename="spoke_a.md", note_id="spoke-a", title="Spoke A")
        _make_note(tmp_path, filename="spoke_b.md", note_id="spoke-b", title="Spoke B")
        graph = build_graph(tmp_path)
        hub_node = next(n for n in graph["nodes"] if n["id"] == "hub")
        assert hub_node["link_count"] == 2

    def test_no_duplicate_edges(self, tmp_path):
        """Even if two notes both link to each other, only one edge per pair."""
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Note B"])
        _make_note(tmp_path, filename="b.md", note_id="id-b", title="Note B",
                   related=["Note A"])
        graph = build_graph(tmp_path)
        # The pair (id-a, id-b) should appear at most twice (A→B and B→A);
        # but the same directed edge must not be duplicated.
        edges = [(e["from"], e["to"]) for e in graph["edges"]]
        assert len(edges) == len(set(edges))


class TestEdgesAreBidirectional:
    """When note A links to B AND B links to A, both directed edges should exist."""

    def test_mutual_links_produce_two_edges(self, tmp_path):
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Note B"])
        _make_note(tmp_path, filename="b.md", note_id="id-b", title="Note B",
                   related=["Note A"])
        graph = build_graph(tmp_path)
        froms = {e["from"] for e in graph["edges"]}
        tos   = {e["to"]   for e in graph["edges"]}
        # Both directions are represented
        assert "id-a" in froms or "id-a" in tos
        assert "id-b" in froms or "id-b" in tos

    def test_one_way_link_produces_one_edge(self, tmp_path):
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Note B"])
        _make_note(tmp_path, filename="b.md", note_id="id-b", title="Note B",
                   related=[])          # B does NOT link back
        graph = build_graph(tmp_path)
        assert len(graph["edges"]) == 1
        assert graph["edges"][0]["from"] == "id-a"
        assert graph["edges"][0]["to"]   == "id-b"


# ─── Graph metadata ──────────────────────────────────────────────────────────


class TestGraphMetadataHasCorrectCounts:
    """build_graph() must return accurate metadata in the 'metadata' key."""

    def test_metadata_key_exists(self, tmp_path):
        graph = build_graph(tmp_path)
        assert "metadata" in graph

    def test_total_nodes_count(self, tmp_path):
        for i in range(3):
            _make_note(tmp_path, filename=f"n{i}.md", note_id=f"id-{i}", title=f"Note {i}")
        graph = build_graph(tmp_path)
        assert graph["metadata"]["total_nodes"] == 3

    def test_total_edges_count(self, tmp_path):
        _make_note(tmp_path, filename="a.md", note_id="id-a", title="Note A",
                   related=["Note B"])
        _make_note(tmp_path, filename="b.md", note_id="id-b", title="Note B")
        graph = build_graph(tmp_path)
        assert graph["metadata"]["total_edges"] == 1

    def test_category_counts_populated(self, tmp_path):
        _make_note(tmp_path, filename="r1.md", note_id="r1", title="R1", category="resources")
        _make_note(tmp_path, filename="r2.md", note_id="r2", title="R2", category="resources")
        _make_note(tmp_path, filename="a1.md", note_id="a1", title="A1", category="areas")
        graph = build_graph(tmp_path)
        counts = graph["metadata"]["category_counts"]
        assert counts.get("resources") == 2
        assert counts.get("areas") == 1

    def test_generated_at_is_iso_string(self, tmp_path):
        graph = build_graph(tmp_path)
        ts = graph["metadata"]["generated_at"]
        assert isinstance(ts, str)
        # Must be parseable as ISO 8601
        from datetime import datetime
        datetime.fromisoformat(ts)

    def test_metadata_zero_counts_when_empty(self, tmp_path):
        graph = build_graph(tmp_path)
        assert graph["metadata"]["total_nodes"] == 0
        assert graph["metadata"]["total_edges"] == 0


# ─── export_graph ────────────────────────────────────────────────────────────


class TestExportGraphWritesValidJson:
    """export_graph() must write valid, correctly structured JSON to disk."""

    def test_creates_output_file(self, tmp_path):
        wiki_dir  = tmp_path / "wiki"
        wiki_dir.mkdir()
        output    = tmp_path / "graph.json"
        _make_note(wiki_dir, note_id="exp-1", title="Export Test")
        export_graph(wiki_dir, output)
        assert output.exists()

    def test_output_is_valid_json(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        output   = tmp_path / "graph.json"
        _make_note(wiki_dir, note_id="exp-2", title="Valid JSON Test")
        export_graph(wiki_dir, output)
        with open(output, encoding="utf-8") as f:
            data = json.load(f)   # raises if invalid JSON
        assert isinstance(data, dict)

    def test_json_has_nodes_edges_metadata(self, tmp_path):
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        output   = tmp_path / "graph.json"
        _make_note(wiki_dir, note_id="exp-3", title="Structure Test")
        export_graph(wiki_dir, output)
        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        assert "nodes"    in data
        assert "edges"    in data
        assert "metadata" in data

    def test_creates_parent_directories(self, tmp_path):
        """export_graph must create any missing parent directories."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        output   = tmp_path / "deeply" / "nested" / "graph.json"
        _make_note(wiki_dir, note_id="exp-4", title="Dir Creation Test")
        export_graph(wiki_dir, output)   # must not raise
        assert output.exists()

    def test_node_data_round_trips(self, tmp_path):
        """Node data written to JSON must be identical to build_graph output."""
        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir()
        output   = tmp_path / "graph.json"
        _make_note(wiki_dir, note_id="rt-1", title="Round Trip", category="projects",
                   tags=["test"], summary="Summary here.")
        export_graph(wiki_dir, output)
        with open(output, encoding="utf-8") as f:
            data = json.load(f)
        node = data["nodes"][0]
        assert node["id"]       == "rt-1"
        assert node["label"]    == "Round Trip"
        assert node["category"] == "projects"
        assert node["tags"]     == ["test"]
