"""
SecondSelf — Wiki Writer (Step 2.4)

Transforms a raw capture + ClassificationResult into an organised markdown
note stored at wiki/{category}/{slug}.md.

Public API:
  - write_wiki_note()  → create / overwrite a wiki note and return its Path
  - slugify()          → convert any string to a filesystem-safe slug
"""

from __future__ import annotations

import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from secondself.classify import ClassificationResult
from secondself.config import WIKI_DIR


# ─── Public API ────────────────────────────────────────────────────────────


def write_wiki_note(
    capture: dict,
    classification: ClassificationResult,
    related: list[dict],
) -> Path:
    """Create a markdown note in ``wiki/{category}/{slug}.md``.

    The note consists of:
    1. YAML frontmatter — ``id``, ``title``, ``category``, ``tags``,
       ``created``, ``source``, ``confidence``
    2. Markdown body — heading, summary blockquote, original content
    3. ``## Related Notes`` section with ``[[wiki-links]]``

    Filename conflicts are handled by appending ``-2``, ``-3``, etc. to the
    slug until a free name is found.  If the note's ID already has a file,
    that file is *overwritten* in-place (idempotent re-processing).

    Args:
        capture:        Raw capture dict loaded from ``raw/{date}_{id}.json``.
        classification: Result of :func:`~secondself.classify.classify_capture`.
        related:        List of related-note dicts from
                        :func:`~secondself.linker.find_related` — each with
                        ``id``, ``title``, and ``similarity`` keys.

    Returns:
        The :class:`~pathlib.Path` of the written wiki note.
    """
    capture_id: str = capture["id"]
    title: str = _resolve_title(capture, classification)
    category: str = classification.category  # one of PARA_CATEGORIES
    tags: list[str] = classification.tags
    summary: str = classification.summary
    timestamp: str = capture.get("timestamp", datetime.now(tz=timezone.utc).isoformat())
    source: str = _resolve_source(capture)

    # 1. Choose the target directory and generate a conflict-free slug/path.
    category_dir: Path = WIKI_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)

    wiki_path: Path = _resolve_wiki_path(
        category_dir=category_dir,
        capture_id=capture_id,
        title=title,
    )

    # 2. Build YAML frontmatter.
    tags_yaml = _format_tags_yaml(tags)
    frontmatter = (
        "---\n"
        f"id: {capture_id}\n"
        f"title: \"{_escape_yaml_string(title)}\"\n"
        f"category: {category}\n"
        f"tags: {tags_yaml}\n"
        f"created: {timestamp}\n"
        f"source: {source}\n"
        f"confidence: {classification.confidence:.2f}\n"
        "---\n"
    )

    # 3. Build markdown body.
    body = _build_body(
        title=title,
        summary=summary,
        capture=capture,
        related=related,
    )

    # 4. Write the complete note.
    wiki_path.write_text(frontmatter + body, encoding="utf-8")

    return wiki_path


def slugify(text: str) -> str:
    """Convert *text* into a filesystem-safe lowercase slug.

    Examples::

        >>> slugify("Attention Is All You Need!")
        'attention-is-all-you-need'
        >>> slugify("PARA method: Projects, Areas, Resources, Archives")
        'para-method-projects-areas-resources-archives'
    """
    text = text.lower().strip()
    # Replace common separators with a hyphen placeholder before stripping
    text = re.sub(r"[:\|/\\]", "-", text)
    # Remove all remaining non-word, non-space, non-hyphen characters
    text = re.sub(r"[^\w\s-]", "", text)
    # Collapse any run of whitespace / underscores into a single hyphen
    text = re.sub(r"[\s_]+", "-", text)
    # Collapse multiple consecutive hyphens
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")


# ─── Private helpers ───────────────────────────────────────────────────────


def _resolve_title(capture: dict, classification: ClassificationResult) -> str:
    """Pick the best available title in priority order:

    1. Classification ``suggested_title`` (LLM-generated, most descriptive)
    2. ``metadata.title`` from the raw capture (auto-extracted at capture time)
    3. First 60 chars of text content (hard fallback)
    """
    # Priority 1 — LLM-suggested title
    if classification.suggested_title and classification.suggested_title.strip():
        return classification.suggested_title.strip()

    # Priority 2 — metadata title stored at capture time
    meta_title = capture.get("metadata", {}).get("title", "").strip()
    if meta_title:
        return meta_title

    # Priority 3 — first 60 chars of content text
    content_text = _extract_content_text(capture)
    if content_text:
        first_line = content_text.split("\n")[0].strip()
        return first_line[:60] or "Untitled Note"

    return "Untitled Note"


def _resolve_source(capture: dict) -> str:
    """Build a source string suitable for frontmatter.

    - URL captures: the raw URL
    - File captures: the original file path
    - Note captures: ``"cli"``
    """
    cap_type = capture.get("type", "note")
    content = capture.get("content", {})

    if cap_type == "url":
        return content.get("url", "cli")
    if cap_type == "file":
        return content.get("file_path", "cli")
    return capture.get("source", "cli")


def _extract_content_text(capture: dict) -> str:
    """Return the primary text content of the capture regardless of type."""
    content = capture.get("content", {})
    cap_type = capture.get("type", "note")

    if cap_type == "url":
        url_text = content.get("text", "")
        url = content.get("url", "")
        if url:
            return f"{url}\n\n{url_text}" if url_text else url
        return url_text

    if cap_type == "file":
        file_content = content.get("file_content", "")
        file_path = content.get("file_path", "")
        if file_content:
            return file_content
        return f"File: {file_path}" if file_path else ""

    # note (default)
    return content.get("text", "")


def _resolve_wiki_path(
    category_dir: Path,
    capture_id: str,
    title: str,
) -> Path:
    """Return a conflict-free path for this note.

    If a note already exists for *capture_id* (identified by scanning
    frontmatter ``id:`` fields), that file is returned directly so
    re-processing overwrites it rather than creating a duplicate.

    Otherwise a slug-based name is generated, with ``-2``, ``-3`` …
    suffixes to avoid collisions with pre-existing unrelated files.
    """
    # Check if this capture already has a wiki file (re-processing case).
    existing = _find_existing_by_id(category_dir, capture_id)
    if existing:
        return existing

    base_slug = slugify(title) or capture_id[:8]
    candidate = category_dir / f"{base_slug}.md"

    if not candidate.exists():
        return candidate

    # Conflict resolution: try -2, -3, …
    counter = 2
    while True:
        candidate = category_dir / f"{base_slug}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1


def _find_existing_by_id(directory: Path, capture_id: str) -> Path | None:
    """Scan *directory* for a ``.md`` file whose frontmatter ``id`` matches."""
    for md_file in directory.glob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if line.strip().startswith("id:"):
                    file_id = line.split(":", 1)[1].strip()
                    if file_id == capture_id:
                        return md_file
    return None


def _format_tags_yaml(tags: list[str]) -> str:
    """Render tags as an inline YAML sequence, e.g. ``["ai", "nlp"]``."""
    if not tags:
        return "[]"
    quoted = ", ".join(f'"{t}"' for t in tags)
    return f"[{quoted}]"


def _escape_yaml_string(text: str) -> str:
    """Escape double-quotes inside a YAML double-quoted string."""
    return text.replace('"', '\\"')


def _build_body(
    title: str,
    summary: str,
    capture: dict,
    related: list[dict],
) -> str:
    """Assemble the markdown body below the frontmatter block.

    Structure::

        # Title

        > Summary

        ## Content

        <original text>

        ## Related Notes

        - [[Note A]]
        - [[Note B]]
    """
    parts: list[str] = []

    # ── Heading ─────────────────────────────────────────────────────────────
    parts.append(f"# {title}\n")

    # ── Summary blockquote ──────────────────────────────────────────────────
    if summary and summary.strip():
        parts.append(f"\n> {summary.strip()}\n")

    # ── Content section ─────────────────────────────────────────────────────
    content_text = _extract_content_text(capture)
    if content_text and content_text.strip():
        parts.append("\n## Content\n")
        # Wrap long plain-text paragraphs; leave markdown/code as-is
        wrapped = _smart_wrap(content_text.strip())
        parts.append(f"\n{wrapped}\n")

    # ── Related Notes section ───────────────────────────────────────────────
    parts.append("\n## Related Notes\n")
    if related:
        link_lines = "\n".join(f"- [[{r['title']}]]" for r in related)
        parts.append(f"\n{link_lines}\n")

    return "\n".join(parts)


def _smart_wrap(text: str, width: int = 100) -> str:
    """Wrap plain-text lines to *width* characters but leave code fences,
    blockquotes, headings, list items, and URLs as-is.

    Lines that start with a Markdown special character or are very short
    are passed through unchanged to avoid breaking structure.
    """
    _MD_SPECIAL_START = re.compile(r"^(```|~~~|#|>|-|\*|\d+\.|https?://|\s*$)")
    output_lines: list[str] = []

    for line in text.splitlines():
        if _MD_SPECIAL_START.match(line) or len(line) <= width:
            output_lines.append(line)
        else:
            # Wrap plain paragraph text
            wrapped = textwrap.fill(line, width=width)
            output_lines.append(wrapped)

    return "\n".join(output_lines)
