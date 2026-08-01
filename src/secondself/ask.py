"""
SecondSelf — RAG Ask Pipeline (Step 4.1)

Implements Retrieval-Augmented Generation (RAG) over the personal knowledge base:

  ask(question, engine) → AskResponse
    1. Embed the question (timed separately)
    2. Retrieve top-K similar notes from ChromaDB (timed separately)
    3. Load full note content from wiki/
    4. Build a grounded RAG prompt (system + context + question)
    5. Call Groq LLM for a synthesised answer (timed)
    6. Determine confidence from the top result's similarity score
    7. Return AskResponse with answer, citations, confidence, and all timings

Confidence thresholds (per implementation plan):
  - "high"   : top similarity > 0.8
  - "medium" : top similarity 0.65 – 0.8
  - "low"    : top similarity < 0.65
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

from secondself.config import LLM_MODEL, TOP_K_RETRIEVAL, WIKI_DIR
from secondself.embed import EmbeddingEngine


# ─── Data classes ────────────────────────────────────────────────────────────


@dataclass
class SourceNote:
    """A single source note cited in an AskResponse."""

    id: str
    title: str
    similarity: float
    excerpt: str  # First ~300 chars of content used as context


@dataclass
class AskResponse:
    """Complete response from the RAG ask() pipeline."""

    answer: str
    sources: list[SourceNote]
    confidence: str                  # "high" | "medium" | "low"
    query_embedding_time_ms: float
    retrieval_time_ms: float
    llm_time_ms: float


# ─── Public API ──────────────────────────────────────────────────────────────


def ask(question: str, engine: EmbeddingEngine) -> AskResponse:
    """Answer *question* using RAG over the personal knowledge base.

    Steps
    -----
    1. Embed the question — timed independently.
    2. Query ChromaDB for the top-K most similar notes — timed independently.
    3. Load the full wiki markdown content for each retrieved note.
    4. Build a grounded RAG prompt (system + context + question).
    5. Call the Groq LLM and time the generation.
    6. Determine confidence from the top result's similarity score:
       - "high"   : similarity > 0.8
       - "medium" : 0.65 ≤ similarity ≤ 0.8
       - "low"    : similarity < 0.65
    7. Return an :class:`AskResponse` with answer, sources, and all timings.

    Args:
        question: Natural-language question from the user.
        engine:   An initialised :class:`~secondself.embed.EmbeddingEngine`.

    Returns:
        :class:`AskResponse` with a synthesised answer and source citations.

    Raises:
        ValueError: If ``GROQ_API_KEY`` is not set in the environment.
    """
    load_dotenv()
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not found in environment. "
            "Please add it to your .env file."
        )

    client = Groq(api_key=api_key)

    # ── Guard: empty knowledge base ───────────────────────────────────────────
    if engine.collection.count() == 0:
        return AskResponse(
            answer=(
                "Your knowledge base is empty. "
                "Run `secondself process` first to populate it."
            ),
            sources=[],
            confidence="low",
            query_embedding_time_ms=0.0,
            retrieval_time_ms=0.0,
            llm_time_ms=0.0,
        )

    # ── Step 1: Embed the question ────────────────────────────────────────────
    t0 = time.perf_counter()
    query_vector = engine.embed_text(question)
    query_embedding_time_ms = (time.perf_counter() - t0) * 1000

    # ── Step 2: Retrieve top-K notes from ChromaDB (use pre-built vector) ─────
    t1 = time.perf_counter()
    n = min(TOP_K_RETRIEVAL, engine.collection.count())
    chroma_results = engine.collection.query(
        query_embeddings=[query_vector],
        n_results=n,
        include=["documents", "metadatas", "distances"],
    )
    raw_results = EmbeddingEngine._format_results(chroma_results)
    retrieval_time_ms = (time.perf_counter() - t1) * 1000

    # ── Step 3: Load full content of matched notes from wiki/ ─────────────────
    sources: list[SourceNote] = []
    context_blocks: list[str] = []

    for result in raw_results:
        note_id    = result["id"]
        metadata   = result.get("metadata", {})
        title      = metadata.get("title", note_id[:8])
        similarity = result["similarity"]

        # Prefer full wiki content for richer context; fallback to stored doc
        full_text = _load_wiki_content(WIKI_DIR, note_id, title)
        if not full_text:
            full_text = result.get("document", "")

        excerpt = (full_text[:300] + "…") if len(full_text) > 300 else full_text

        sources.append(SourceNote(
            id=note_id,
            title=title,
            similarity=similarity,
            excerpt=excerpt,
        ))

        context_blocks.append(
            f"### [{title}] (similarity: {similarity:.2f})\n{full_text[:1500]}"
        )

    # ── Step 4: Build the RAG prompt ──────────────────────────────────────────
    context_text = (
        "\n\n---\n\n".join(context_blocks)
        if context_blocks
        else "(no relevant notes found)"
    )

    system_prompt = (
        "You are a personal AI second brain assistant. "
        "Answer the user's question using ONLY the notes provided below "
        "from their personal knowledge base. "
        "Be concise but thorough. "
        "If the notes don't fully answer the question, say so honestly — "
        "do NOT invent information. "
        "Always cite the note title(s) you drew from using the format: "
        "[Source: Note Title]."
    )

    user_prompt = (
        f"## My Knowledge Base Notes\n\n"
        f"{context_text}\n\n"
        f"---\n\n"
        f"## Question\n\n"
        f"{question}\n\n"
        f"## Instructions\n"
        f"- Answer using ONLY the notes above.\n"
        f"- Cite sources like: [Source: Note Title]\n"
        f"- If unsure, say: \"My notes don't fully cover this.\"\n"
        f"- Keep the answer focused and under 200 words."
    )

    # ── Step 5: Call Groq LLM ─────────────────────────────────────────────────
    t2 = time.perf_counter()

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.3,
        max_tokens=512,
    )

    llm_time_ms = (time.perf_counter() - t2) * 1000

    answer = response.choices[0].message.content or "(no response)"

    # ── Step 6: Determine confidence from top result similarity ───────────────
    top_similarity = sources[0].similarity if sources else 0.0

    if top_similarity > 0.8:
        confidence = "high"
    elif top_similarity >= 0.65:
        confidence = "medium"
    else:
        confidence = "low"

    # ── Step 7: Return AskResponse ────────────────────────────────────────────
    return AskResponse(
        answer=answer,
        sources=sources,
        confidence=confidence,
        query_embedding_time_ms=round(query_embedding_time_ms, 1),
        retrieval_time_ms=round(retrieval_time_ms, 1),
        llm_time_ms=round(llm_time_ms, 1),
    )


# ─── Internal helpers ─────────────────────────────────────────────────────────


def _load_wiki_content(wiki_dir: Path, capture_id: str, title: str) -> str:
    """Load the body content of a wiki note, identified by capture_id or title.

    Search strategy:
      1. Scan all .md files and match by the ``id`` frontmatter field.
      2. Fallback: match by slug derived from *title*.

    Args:
        wiki_dir:   Root wiki directory (searched recursively).
        capture_id: The capture UUID to look up.
        title:      Note title used for slug-based fallback.

    Returns:
        Clean plain-text body of the note, or ``""`` if not found.
    """
    # Pass 1 — match by frontmatter id
    for md_file in wiki_dir.rglob("*.md"):
        try:
            raw = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if line.strip().startswith("id:") and capture_id in line:
                    return _extract_body(raw, fm_match.end())

    # Pass 2 — fuzzy match by slug derived from title
    slug = _slugify(title)
    for md_file in wiki_dir.rglob("*.md"):
        if md_file.stem == slug:
            try:
                raw = md_file.read_text(encoding="utf-8")
                fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
                start = fm_match.end() if fm_match else 0
                return _extract_body(raw, start)
            except OSError:
                pass

    return ""


def _extract_body(raw: str, start: int) -> str:
    """Return clean plain-text body from a wiki note, stripping Markdown syntax.

    Args:
        raw:   Full file content.
        start: Character index where the body begins (after frontmatter).

    Returns:
        Cleaned plain-text content suitable for LLM context.
    """
    body = raw[start:].strip()

    # Remove Markdown headings (##, ###, etc.)
    body = re.sub(r"^#{1,6}\s+.*$", "", body, flags=re.MULTILINE)
    # Remove blockquote markers (> …)
    body = re.sub(r"^> ", "", body, flags=re.MULTILINE)
    # Unwrap [[wiki-links]] — keep the link text
    body = re.sub(r"\[\[(.+?)\]\]", r"\1", body)
    # Remove **bold** and *italic* markers
    body = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", body)
    # Remove list markers (- item, * item, 1. item)
    body = re.sub(r"^\s*[-*]\s+", "", body, flags=re.MULTILINE)
    body = re.sub(r"^\s*\d+\.\s+", "", body, flags=re.MULTILINE)
    # Collapse runs of blank lines
    body = re.sub(r"\n{3,}", "\n\n", body)

    return body.strip()


def _slugify(text: str) -> str:
    """Convert a note title to a filesystem-safe slug for file lookup.

    Matches the slugification logic used by :mod:`~secondself.wiki_writer`.

    Args:
        text: The note title to slugify.

    Returns:
        A lowercase, hyphen-separated slug.
    """
    text = text.lower().strip()
    text = re.sub(r"[:|/\\]", "-", text)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-")
