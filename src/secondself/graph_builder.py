"""
SecondSelf — Graph Builder (Step 3.1)

Parses wiki notes and builds a JSON graph representation for visualization.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path


def parse_wiki_note(file_path: Path) -> dict:
    """Parse a wiki markdown file into a node dict."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        content = ""

    # 1. Parse frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    fm_data = {}
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                fm_data[key.strip()] = val.strip().strip('"').strip("'")

    # Safely parse tags
    tags_str = fm_data.get("tags", "[]")
    if tags_str.startswith("[") and tags_str.endswith("]"):
        try:
            tags = json.loads(tags_str)
        except json.JSONDecodeError:
            tags = []
    else:
        tags = []

    node_id = fm_data.get("id", file_path.stem)
    title = fm_data.get("title", file_path.stem)
    category = fm_data.get("category", "resources")
    created = fm_data.get("created", "")

    # 2. Extract content body and summary
    after_fm = content[fm_match.end():] if fm_match else content

    summary = ""
    summary_match = re.search(r"^> (.*?)$", after_fm, re.MULTILINE)
    if summary_match:
        summary = summary_match.group(1).strip()

    content_preview = ""
    word_count = 0
    content_match = re.search(r"## Content\n(.*?)(?:## Related Notes|\Z)", after_fm, re.DOTALL)
    if content_match:
        full_content = content_match.group(1).strip()
        content_preview = full_content[:200] + ("..." if len(full_content) > 200 else "")
        word_count = len(full_content.split())
    else:
        # Fallback if no ## Content section
        text_lines = [
            line.strip()
            for line in after_fm.splitlines()
            if line.strip() and not line.startswith(("#", ">"))
        ]
        if text_lines:
            full_content = " ".join(text_lines)
            content_preview = full_content[:200] + ("..." if len(full_content) > 200 else "")
            word_count = len(full_content.split())

    # 3. Parse related notes
    related_notes = []
    related_match = re.search(r"## Related Notes\n(.*)", after_fm, re.DOTALL)
    if related_match:
        related_text = related_match.group(1)
        related_notes = re.findall(r"\[\[(.*?)\]\]", related_text)

    return {
        "id": node_id,
        "label": title,
        "category": category,
        "tags": tags,
        "summary": summary,
        "content_preview": content_preview,
        "created": created,
        "word_count": word_count,
        "links": related_notes,
    }


def build_graph(wiki_dir: Path) -> dict:
    """Build complete graph JSON from all wiki notes."""
    nodes = []
    edges = []

    # 1. Scan all .md files in wiki/ recursively
    for md_file in wiki_dir.rglob("*.md"):
        node = parse_wiki_note(md_file)
        nodes.append(node)

    # 2. Build a lookup for title -> node_id
    title_to_id = {node["label"]: node["id"] for node in nodes}

    edge_set = set()
    category_counts = {}

    for node in nodes:
        cat = node["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

        node_id = node["id"]
        link_count = 0

        # 3. Build edges from [[links]]
        for link_title in node.get("links", []):
            target_id = title_to_id.get(link_title)
            if target_id and target_id != node_id:
                link_count += 1
                edge_tuple = (node_id, target_id)
                if edge_tuple not in edge_set:
                    edge_set.add(edge_tuple)
                    edges.append({"from": node_id, "to": target_id})

        # 4. Compute link_count per node
        node["link_count"] = link_count
        # Remove links as it's not needed in final graph JSON
        if "links" in node:
            del node["links"]

    # 5. Build metadata
    metadata = {
        "total_nodes": len(nodes),
        "total_edges": len(edges),
        "category_counts": category_counts,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    }

    # 6. Return standard dict
    return {
        "nodes": nodes,
        "edges": edges,
        "metadata": metadata,
    }


def export_graph(wiki_dir: Path, output_path: Path) -> None:
    """Build graph and write to JSON file."""
    graph_data = build_graph(wiki_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2)
