"""
SecondSelf — FastAPI Server (Step 4.2)

Serves the web UI and all REST API endpoints:

  GET  /                  → web/index.html  (SPA shell)
  GET  /{file}            → static files from web/ (js, css)
  GET  /api/health        → health check (used by deployment platforms)
  GET  /api/graph         → knowledge graph JSON (cached data/graph.json)
  POST /api/ask           → RAG Q&A (calls ask.py pipeline)
  POST /api/capture       → capture a note/url/file from the web UI
  POST /api/process       → (re)process raw captures into wiki + embeddings
  GET  /api/notes         → list all wiki notes (filter by category/tag)
  GET  /api/notes/{id}    → full content of one note
  GET  /api/search        → semantic search
  GET  /api/stats         → dashboard statistics

Run with:
    uv run uvicorn secondself.server:app --reload --host 0.0.0.0 --port 8000
or:
    uv run secondself serve
"""

from __future__ import annotations

import json
import re
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from secondself.config import (
    GRAPH_JSON, PARA_CATEGORIES, RAW_DIR, WIKI_DIR, WEB_DIR,
)
from secondself.graph_builder import build_graph, export_graph


# ── Lazy singleton — loaded on first /api/ask or /api/search call ─────────────
_engine = None


def _get_engine():
    """Return a shared EmbeddingEngine, initialising it once."""
    global _engine
    if _engine is None:
        from secondself.embed import EmbeddingEngine
        _engine = EmbeddingEngine()
    return _engine


# ── Lifespan: pre-warm embedding engine on startup ────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    Application lifespan handler.

    On startup:
      - Pre-warms the embedding engine so the first /api/ask call doesn't
        pay the sentence-transformers model-load cost.
      - Rebuilds data/graph.json if wiki/ is newer than the cached file.

    On shutdown:
      - Nothing required — ChromaDB persists automatically.
    """
    # Rebuild graph if wiki notes are newer than cached graph.json
    try:
        _maybe_rebuild_graph()
    except Exception:
        pass  # Non-fatal — graph will be rebuilt on next /api/graph request

    # Pre-warm embedding engine in background (non-blocking best-effort)
    try:
        _get_engine()
    except Exception:
        pass  # Non-fatal — will be initialised on first request

    yield  # Server is running


def _maybe_rebuild_graph() -> None:
    """Rebuild data/graph.json only when wiki/ contains newer files than the cache."""
    if not WIKI_DIR.exists():
        return

    md_files = list(WIKI_DIR.rglob("*.md"))
    if not md_files:
        return

    newest_wiki_mtime = max(f.stat().st_mtime for f in md_files)

    if GRAPH_JSON.exists():
        graph_mtime = GRAPH_JSON.stat().st_mtime
        if graph_mtime >= newest_wiki_mtime:
            return  # Cache is still fresh

    export_graph(WIKI_DIR, GRAPH_JSON)


# ─── Pydantic request models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str


class CaptureRequest(BaseModel):
    type: str     # "note" | "url" | "file"
    content: str  # the text, URL, or file path


class ProcessRequest(BaseModel):
    capture_id: Optional[str] = None  # None → process all unprocessed


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SecondSelf",
    description="Your Personal AI Second Brain",
    version="0.1.0",
    lifespan=lifespan,
)

# ── CORS — allow all origins in development ───────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Static files ─────────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


# ─── Root — SPA shell ─────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Serve web/index.html."""
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(
            status_code=404,
            detail="web/index.html not found. Run Phase 3 first.",
        )
    return FileResponse(str(index))


@app.get("/{filename}", include_in_schema=False)
async def serve_web_file(filename: str):
    """Serve any single-segment file from web/ (graph.js, style.css, chat.js …)."""
    # This catch-all must not shadow /api/* — those are multi-segment paths so
    # they will never reach this handler, but guard explicitly for safety.
    if filename.startswith("api"):
        raise HTTPException(status_code=404)
    filepath = WEB_DIR / filename
    if filepath.exists() and filepath.is_file():
        return FileResponse(str(filepath))
    raise HTTPException(status_code=404, detail=f"{filename} not found in web/")


# ─── API: Health ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def api_health():
    """
    Health check endpoint.

    Used by Railway, Render, and other deployment platforms to verify the
    server is running and responsive.  Returns a lightweight status payload.
    """
    return JSONResponse(content={
        "status": "ok",
        "version": "0.1.0",
        "wiki_notes": sum(
            1 for _ in WIKI_DIR.rglob("*.md")
        ) if WIKI_DIR.exists() else 0,
    })


# ─── API: Graph ───────────────────────────────────────────────────────────────

@app.get("/api/graph")
async def api_graph():
    """
    Return the knowledge graph JSON.

    Serves the cached ``data/graph.json``.  Rebuilds it first if:
      - The file does not exist yet, or
      - Any wiki note is newer than the cached file.

    This keeps the graph current without paying a full rebuild on every
    browser refresh.
    """
    if not WIKI_DIR.exists():
        raise HTTPException(
            status_code=503,
            detail="wiki/ directory not found. Run `secondself process` first.",
        )

    try:
        _maybe_rebuild_graph()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph rebuild failed: {exc}")

    # Serve from cache if available, otherwise build in memory
    if GRAPH_JSON.exists():
        try:
            with open(GRAPH_JSON, encoding="utf-8") as f:
                graph_data = json.load(f)
            return JSONResponse(content=graph_data)
        except Exception:
            pass  # Fallback to in-memory build below

    try:
        graph_data = build_graph(WIKI_DIR)
        return JSONResponse(content=graph_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── API: Ask (RAG) ───────────────────────────────────────────────────────────

@app.post("/api/ask")
async def api_ask(req: AskRequest):
    """
    Answer a natural-language question using RAG over the knowledge base.

    Returns the synthesised answer, source citations, confidence level,
    and timing breakdown (embedding ms, retrieval ms, LLM ms).
    """
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question must not be empty")

    try:
        from secondself.ask import ask
        engine = _get_engine()

        if engine.collection.count() == 0:
            return JSONResponse(content={
                "answer": (
                    "Your knowledge base is empty. "
                    "Run `secondself process` first to populate it."
                ),
                "sources": [],
                "confidence": "low",
                "query_embedding_time_ms": 0,
                "retrieval_time_ms": 0,
                "llm_time_ms": 0,
            })

        response = ask(question, engine)

        # Serialise dataclasses (asdict works recursively for nested dataclasses)
        return JSONResponse(content={
            "answer": response.answer,
            "sources": [asdict(s) for s in response.sources],
            "confidence": response.confidence,
            "query_embedding_time_ms": response.query_embedding_time_ms,
            "retrieval_time_ms": response.retrieval_time_ms,
            "llm_time_ms": response.llm_time_ms,
        })

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── API: Capture ─────────────────────────────────────────────────────────────

@app.post("/api/capture")
async def api_capture(req: CaptureRequest):
    """
    Capture a new item (note / URL / file) from the web UI.

    Immediately runs the full processing pipeline:
    capture → classify → embed → find_related → write_wiki → backlinks.

    Returns the new note's id, category, title, and wiki path.
    """
    try:
        from secondself.capture import capture_note, capture_url, capture_file
        from secondself.classify import classify_capture
        from secondself.linker import find_related, update_backlinks
        from secondself.wiki_writer import write_wiki_note

        cap_type = req.type.lower()

        if cap_type == "note":
            capture = capture_note(req.content)
        elif cap_type == "url":
            capture = capture_url(req.content)
        elif cap_type == "file":
            capture = capture_file(req.content)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown capture type '{req.type}'. Use: note, url, or file.",
            )

        # 1. Classify
        engine = _get_engine()
        classification = classify_capture(capture)

        # 2. Embed + store in ChromaDB
        content_text = _extract_text(capture)
        engine.store(
            capture_id=capture["id"],
            text=content_text,
            metadata={
                "title": classification.suggested_title,
                "category": classification.category,
                "tags": json.dumps(classification.tags),
                "timestamp": capture.get("timestamp", ""),
            },
        )

        # 3. Find related notes
        try:
            related = find_related(capture["id"], engine)
        except (ValueError, Exception):
            related = []

        # 4. Write wiki note
        wiki_path = write_wiki_note(capture, classification, related)

        # 5. Update backlinks
        if related:
            update_backlinks(
                wiki_dir=WIKI_DIR,
                source_title=classification.suggested_title,
                related=related,
            )

        # 6. Invalidate graph cache so next /api/graph reflects the new note
        _invalidate_graph_cache()

        return JSONResponse(content={
            "id": capture["id"],
            "status": "processed",
            "category": classification.category,
            "title": classification.suggested_title,
            "wiki_path": str(wiki_path.relative_to(WIKI_DIR)),
            "tags": classification.tags,
        })

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── API: Process (batch) ─────────────────────────────────────────────────────

@app.post("/api/process")
async def api_process(req: ProcessRequest):
    """
    (Re-)process raw captures into wiki notes + embeddings.

    Body (JSON):
      - ``capture_id`` (optional): process only this capture.
        If omitted, process all captures not yet in wiki/.

    Returns a summary of what was processed.
    """
    try:
        from secondself.capture import list_captures, get_capture
        from secondself.classify import classify_capture
        from secondself.linker import find_related, update_backlinks
        from secondself.wiki_writer import write_wiki_note

        engine = _get_engine()
        processed = []
        skipped = []
        errors = []

        # Determine which captures to process
        if req.capture_id:
            capture = get_capture(req.capture_id)
            if not capture:
                raise HTTPException(
                    status_code=404,
                    detail=f"Capture '{req.capture_id}' not found",
                )
            captures_to_process = [capture]
        else:
            captures_to_process = list_captures()

        for capture in captures_to_process:
            cap_id = capture["id"]
            try:
                # Skip if already embedded (use ChromaDB as the source of truth)
                existing = engine.collection.get(ids=[cap_id], include=[])
                if existing["ids"]:
                    skipped.append(cap_id[:8])
                    continue

                # Classify
                classification = classify_capture(capture)

                # Embed
                content_text = _extract_text(capture)
                engine.store(
                    capture_id=cap_id,
                    text=content_text,
                    metadata={
                        "title": classification.suggested_title,
                        "category": classification.category,
                        "tags": json.dumps(classification.tags),
                        "timestamp": capture.get("timestamp", ""),
                    },
                )

                # Find related + write wiki + backlinks
                try:
                    related = find_related(cap_id, engine)
                except Exception:
                    related = []

                write_wiki_note(capture, classification, related)

                if related:
                    update_backlinks(
                        wiki_dir=WIKI_DIR,
                        source_title=classification.suggested_title,
                        related=related,
                    )

                processed.append({
                    "id": cap_id[:8],
                    "title": classification.suggested_title,
                    "category": classification.category,
                })

            except Exception as exc:
                errors.append({"id": cap_id[:8], "error": str(exc)})

        # Invalidate graph cache
        _invalidate_graph_cache()

        return JSONResponse(content={
            "processed": len(processed),
            "skipped": len(skipped),
            "errors": len(errors),
            "details": {
                "processed": processed,
                "skipped": skipped,
                "errors": errors,
            },
        })

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── API: Notes — list ────────────────────────────────────────────────────────

@app.get("/api/notes")
async def api_list_notes(
    category: Optional[str] = Query(None, description="Filter by PARA category"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
):
    """
    List all wiki notes with optional filters.

    Returns a lightweight summary for each note (id, title, category, tags,
    created, word_count, path) — NOT the full markdown content.

    Query parameters:
      - ``category``: one of projects | areas | resources | archives
      - ``tag``: exact tag string match
    """
    if not WIKI_DIR.exists():
        return JSONResponse(content={"notes": [], "total": 0})

    notes = []
    for md_file in WIKI_DIR.rglob("*.md"):
        try:
            note_meta = _parse_note_meta(md_file)
        except Exception:
            continue

        # Apply category filter
        if category and note_meta.get("category") != category:
            continue

        # Apply tag filter
        if tag:
            note_tags = note_meta.get("tags", [])
            if tag not in note_tags:
                continue

        notes.append(note_meta)

    # Sort newest first (ISO timestamp strings sort lexicographically)
    notes.sort(key=lambda n: n.get("created", ""), reverse=True)

    return JSONResponse(content={"notes": notes, "total": len(notes)})


# ─── API: Notes — single ──────────────────────────────────────────────────────

@app.get("/api/notes/{note_id}")
async def api_get_note(note_id: str):
    """
    Return the full markdown content and metadata of a single note.

    Identifies the note by its frontmatter ``id`` field.
    A prefix match is supported — you can pass the first 8 chars of the UUID.
    """
    if not WIKI_DIR.exists():
        raise HTTPException(status_code=404, detail="wiki/ not found")

    for md_file in WIKI_DIR.rglob("*.md"):
        try:
            raw = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not fm_match:
            continue

        for line in fm_match.group(1).splitlines():
            if line.strip().startswith("id:"):
                file_id = line.split(":", 1)[1].strip().strip('"').strip("'")
                if file_id.startswith(note_id):
                    meta = _parse_note_meta(md_file)
                    return JSONResponse(content={
                        "id": file_id,
                        "content": raw,
                        "path": str(md_file.relative_to(WIKI_DIR)),
                        "meta": meta,
                    })

    raise HTTPException(status_code=404, detail=f"Note '{note_id}' not found")


# ─── API: Search ──────────────────────────────────────────────────────────────

@app.get("/api/search")
async def api_search(
    q: str = Query(..., description="Search query"),
    k: int = Query(5, ge=1, le=20, description="Number of results"),
):
    """
    Semantic search over the embedded knowledge base.

    Returns up to *k* results ranked by cosine similarity to the query.
    Each result includes id, document preview, metadata, and similarity score.
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="q must not be empty")

    try:
        engine = _get_engine()

        if engine.collection.count() == 0:
            return JSONResponse(content={"results": [], "query": q, "total": 0})

        results = engine.query_similar(q.strip(), k=k)
        return JSONResponse(content={
            "results": results,
            "query": q,
            "total": len(results),
        })

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ─── API: Stats ───────────────────────────────────────────────────────────────

@app.get("/api/stats")
async def api_stats():
    """
    Dashboard statistics.

    Returns:
      - ``total_notes``:     Number of wiki notes (all PARA categories)
      - ``total_raw``:       Number of raw JSON captures
      - ``total_embedded``:  Number of notes stored in ChromaDB
      - ``by_category``:     Per-category note counts
      - ``recent_captures``: Last 5 captures (id, type, title, timestamp)
    """
    stats: dict = {
        "total_notes": 0,
        "total_raw": 0,
        "total_embedded": 0,
        "by_category": {},
        "recent_captures": [],
    }

    # Per-category note counts
    if WIKI_DIR.exists():
        for category in PARA_CATEGORIES:
            cat_dir = WIKI_DIR / category
            count = len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0
            stats["by_category"][category] = count
            stats["total_notes"] += count

    # Raw capture count + 5 most recent
    if RAW_DIR.exists():
        raw_files = sorted(RAW_DIR.glob("*.json"), reverse=True)
        stats["total_raw"] = len(raw_files)

        for rf in raw_files[:5]:
            try:
                data = json.loads(rf.read_text(encoding="utf-8"))
                stats["recent_captures"].append({
                    "id":        data.get("id", "")[:8],
                    "type":      data.get("type", "note"),
                    "title":     data.get("metadata", {}).get("title", ""),
                    "timestamp": data.get("timestamp", ""),
                })
            except Exception:
                pass

    # ChromaDB embedded count
    try:
        stats["total_embedded"] = _get_engine().collection.count()
    except Exception:
        pass

    return JSONResponse(content=stats)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_note_meta(md_file: Path) -> dict:
    """Parse just the frontmatter of a wiki note into a lightweight summary dict.

    Resilient to files without proper YAML frontmatter — returns a minimal
    dict using the file stem as the title rather than raising an exception.
    """
    try:
        raw = md_file.read_text(encoding="utf-8")
    except OSError:
        return {"id": md_file.stem, "title": md_file.stem, "path": str(md_file.name)}

    meta: dict = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)

    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip('"').strip("'")

    # Parse tags from YAML inline list "[\"a\", \"b\"]" or empty "[]"
    tags_str = meta.get("tags", "[]")
    try:
        tags = json.loads(tags_str) if tags_str.startswith("[") else []
    except (json.JSONDecodeError, ValueError):
        tags = []
    meta["tags"] = tags

    # Word count from body (after frontmatter)
    body_start = fm_match.end() if fm_match else 0
    after_fm = raw[body_start:]
    meta["word_count"] = len(after_fm.split())

    # Ensure required keys have fallback values
    meta.setdefault("id", md_file.stem)
    meta.setdefault("title", md_file.stem)
    meta.setdefault("category", "resources")
    meta.setdefault("created", "")

    # Relative path from wiki root
    try:
        meta["path"] = str(md_file.relative_to(WIKI_DIR))
    except ValueError:
        meta["path"] = md_file.name

    return meta


def _extract_text(capture: dict) -> str:
    """Extract embeddable plain text from any capture type dict."""
    content = capture.get("content", {})
    cap_type = capture.get("type", "note")
    if cap_type == "url":
        url = content.get("url", "")
        text = content.get("text", "")
        return f"{url}\n\n{text}" if url else text
    if cap_type == "file":
        return content.get("file_content", "") or content.get("file_path", "")
    return content.get("text", "")


def _invalidate_graph_cache() -> None:
    """Delete data/graph.json so the next /api/graph request rebuilds it."""
    try:
        if GRAPH_JSON.exists():
            GRAPH_JSON.unlink()
    except OSError:
        pass
