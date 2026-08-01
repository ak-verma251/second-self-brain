"""
SecondSelf — Auto-Linker (Step 2.3)

Connects wiki notes to each other using embedding similarity.

Three public functions:
  - find_related()      → query ChromaDB for semantically similar notes
  - insert_links()      → write [[wiki-links]] into a note's Related Notes section
  - update_backlinks()  → add reciprocal links from related notes back to the source
"""

from __future__ import annotations

import re
from pathlib import Path

from secondself.config import MAX_LINKS_PER_NOTE, SIMILARITY_THRESHOLD, WIKI_DIR
from secondself.embed import EmbeddingEngine

# ─── Section header written / searched inside every wiki note ──────────────
_RELATED_HEADER = "## Related Notes"


# ─── Public API ────────────────────────────────────────────────────────────


def find_related(capture_id: str, engine: EmbeddingEngine) -> list[dict]:
    """Return notes that are semantically related to the note identified by
    *capture_id*.

    Args:
        capture_id: The full capture UUID.  The note **must** already be stored
                    in ChromaDB via ``engine.store()`` before calling this.
        engine:     An initialised :class:`~secondself.embed.EmbeddingEngine`.

    Returns:
        A list of result dicts (≤ MAX_LINKS_PER_NOTE items), each containing::

            {
                "id":         str,    # capture ID of the related note
                "title":      str,    # title from stored metadata (may be empty)
                "similarity": float,  # cosine similarity in [0, 1]
            }

        Results are ordered by descending similarity.  Notes that fall below
        ``SIMILARITY_THRESHOLD`` or that are the source note itself are
        excluded.

    Raises:
        ValueError: propagated from
                    :meth:`~secondself.embed.EmbeddingEngine.query_similar_by_id`
                    if *capture_id* is not in the collection.
    """
    # Fetch top-(MAX_LINKS_PER_NOTE + 1) so we always have room to filter.
    raw: list[dict] = engine.query_similar_by_id(
        capture_id, k=MAX_LINKS_PER_NOTE + 1
    )

    related: list[dict] = []
    for result in raw:
        # 1. Skip self-matches (query_similar_by_id already drops the exact
        #    self-match, but guard against any edge-case duplicates).
        if result["id"] == capture_id:
            continue

        # 2. Apply the similarity threshold gate.
        if result["similarity"] < SIMILARITY_THRESHOLD:
            continue

        # 3. Extract the title from stored metadata; fall back to the ID prefix.
        title: str = (
            result.get("metadata", {}).get("title", "")
            or result["id"][:8]
        )

        related.append(
            {
                "id": result["id"],
                "title": title,
                "similarity": result["similarity"],
            }
        )

        # 4. Hard-cap at MAX_LINKS_PER_NOTE.
        if len(related) >= MAX_LINKS_PER_NOTE:
            break

    return related


def insert_links(wiki_path: Path, related: list[dict]) -> None:
    """Insert ``[[wiki-links]]`` into the *Related Notes* section of a wiki note.

    The function is **idempotent** — running it twice for the same set of
    related notes will not create duplicate links.

    Args:
        wiki_path: Absolute path to the target ``.md`` file.
        related:   List of dicts in the same format returned by
                   :func:`find_related`.  At most ``MAX_LINKS_PER_NOTE``
                   entries will be written (extras are silently ignored).
    """
    if not wiki_path.exists():
        return

    if not related:
        return

    content = wiki_path.read_text(encoding="utf-8")

    # ── Locate or create the Related Notes section ──────────────────────────
    header_index = content.find(_RELATED_HEADER)

    if header_index == -1:
        # Section does not exist yet — append it.
        if not content.endswith("\n"):
            content += "\n"
        content += f"\n{_RELATED_HEADER}\n\n"
        header_index = content.find(_RELATED_HEADER)

    # Everything after the header line.
    after_header = content[header_index + len(_RELATED_HEADER):]

    # Collect links that are *already* present so we avoid duplicates.
    existing_links: set[str] = set(re.findall(r"\[\[(.+?)]]", after_header))

    # Build the new link lines to insert (capped at MAX_LINKS_PER_NOTE).
    new_lines: list[str] = []
    for entry in related[:MAX_LINKS_PER_NOTE]:
        title = entry["title"]
        if title not in existing_links:
            new_lines.append(f"- [[{title}]]")

    if not new_lines:
        return  # Nothing new to add.

    # ── Splice the new lines into the content ───────────────────────────────
    # Find the insertion point: right after the header line (and its newline).
    insertion_offset = header_index + len(_RELATED_HEADER)
    # Skip the newline that terminates the header line itself.
    if insertion_offset < len(content) and content[insertion_offset] == "\n":
        insertion_offset += 1

    links_block = "\n".join(new_lines) + "\n"
    content = content[:insertion_offset] + links_block + content[insertion_offset:]

    wiki_path.write_text(content, encoding="utf-8")


def update_backlinks(
    wiki_dir: Path,
    source_title: str,
    related: list[dict],
) -> None:
    """Add a reciprocal ``[[source_title]]`` link into every note listed in
    *related*, maintaining bidirectional links.

    Args:
        wiki_dir:     Root wiki directory (``config.WIKI_DIR``).
        source_title: Title of the *source* note (the one whose backlinks we
                      are propagating).
        related:      Same list as returned by :func:`find_related`.
    """
    for entry in related:
        target_path = _find_wiki_file_by_title(wiki_dir, entry["title"])
        if target_path is None:
            # Related note has not been written to wiki yet — skip.
            continue

        content = target_path.read_text(encoding="utf-8")

        # Locate the Related Notes section.
        header_index = content.find(_RELATED_HEADER)
        if header_index == -1:
            # Section missing in target — append it.
            if not content.endswith("\n"):
                content += "\n"
            content += f"\n{_RELATED_HEADER}\n\n"
            header_index = content.find(_RELATED_HEADER)

        after_header = content[header_index + len(_RELATED_HEADER):]

        # Check if the backlink already exists.
        existing_links: set[str] = set(re.findall(r"\[\[(.+?)]]", after_header))
        if source_title in existing_links:
            continue  # Backlink already present — nothing to do.

        # Insert backlink right after the header line.
        insertion_offset = header_index + len(_RELATED_HEADER)
        if insertion_offset < len(content) and content[insertion_offset] == "\n":
            insertion_offset += 1

        backlink_line = f"- [[{source_title}]]\n"
        content = content[:insertion_offset] + backlink_line + content[insertion_offset:]

        target_path.write_text(content, encoding="utf-8")


# ─── Internal helpers ──────────────────────────────────────────────────────


def _find_wiki_file_by_title(wiki_dir: Path, title: str) -> Path | None:
    """Scan *wiki_dir* recursively for a ``.md`` file whose YAML frontmatter
    ``title`` field matches *title* (case-insensitive).

    Falls back to slug-matching the filename stem against a slugified form of
    *title* if frontmatter is absent or the title doesn't match exactly.

    Returns:
        The first matching :class:`~pathlib.Path`, or ``None`` if not found.
    """
    title_lower = title.lower().strip()

    for md_file in wiki_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")

        # ── Try YAML frontmatter title ──────────────────────────────────────
        fm_match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL
        )
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if line.lower().startswith("title:"):
                    fm_title = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if fm_title.lower() == title_lower:
                        return md_file
                    break  # title key found but didn't match; try filename

        # ── Fall back: compare slugified stem ──────────────────────────────
        slug = _slugify(title)
        if md_file.stem.lower() == slug:
            return md_file

    return None


def _slugify(text: str) -> str:
    """Convert *text* to a filesystem-safe lowercase slug.

    Example::

        >>> _slugify("Attention Is All You Need!")
        'attention-is-all-you-need'
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)       # remove non-word chars
    text = re.sub(r"[\s_]+", "-", text)         # spaces/underscores → hyphens
    text = re.sub(r"-{2,}", "-", text)           # collapse multiple hyphens
    return text.strip("-")
