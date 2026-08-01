"""
SecondSelf — CLI Entry Point

Click-based CLI with command groups for capturing and managing knowledge.
"""

from __future__ import annotations

import json

import click
from rich.console import Console
from rich.table import Table

from secondself.capture import (
    capture_file,
    capture_note,
    capture_url,
    get_capture,
    list_captures,
)

console = Console()


@click.group()
@click.version_option(package_name="secondself")
def main():
    """🧠 SecondSelf — Your Personal AI Second Brain"""
    pass


# ─── Capture Command Group ──────────────────────────────────────────


@main.group()
def capture():
    """📥 Capture a note, URL, or file."""
    pass


@capture.command()
@click.argument("text")
def note(text: str):
    """Capture a text note.

    TEXT is the content of the note to capture.
    """
    try:
        capture_note(text)
    except Exception as e:
        console.print(f"[red]✗ Error capturing note: {e}[/red]")
        raise SystemExit(1)


@capture.command()
@click.argument("url")
def url(url: str):
    """Capture a URL with fetched title and description.

    URL is the web address to capture.
    """
    try:
        capture_url(url)
    except Exception as e:
        console.print(f"[red]✗ Error capturing URL: {e}[/red]")
        raise SystemExit(1)


@capture.command()
@click.argument("file_path", type=click.Path(exists=True))
def file(file_path: str):
    """Capture a file with extracted text content.

    FILE_PATH is the path to the file to capture.
    """
    try:
        capture_file(file_path)
    except Exception as e:
        console.print(f"[red]✗ Error capturing file: {e}[/red]")
        raise SystemExit(1)


# ─── List Command ────────────────────────────────────────────────────


@main.command("list")
def list_cmd():
    """📋 List all captured items."""
    captures = list_captures()

    if not captures:
        console.print("[dim]No captures yet. Use [bold]secondself capture note \"...\"[/bold] to get started.[/dim]")
        return

    table = Table(
        title=f"🧠 SecondSelf — {len(captures)} Captures",
        show_lines=False,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("ID", style="bold", width=10)
    table.add_column("Type", style="magenta", width=6)
    table.add_column("Title / Preview", style="white", min_width=30)
    table.add_column("Timestamp", style="dim", width=20)

    for cap in captures:
        cap_id = cap["id"][:8]
        cap_type = cap.get("type", "?")

        # Build title/preview
        title = cap.get("metadata", {}).get("title", "")
        if not title:
            text = cap.get("content", {}).get("text", "")
            title = text[:60] + ("..." if len(text) > 60 else "")

        # Truncate title for table display
        if len(title) > 60:
            title = title[:57] + "..."

        # Format timestamp
        timestamp = cap.get("timestamp", "")
        if timestamp:
            # Show just date + time, no timezone
            timestamp = timestamp[:19].replace("T", " ")

        # Color-code the type
        type_colors = {"note": "yellow", "url": "blue", "file": "green"}
        type_color = type_colors.get(cap_type, "white")
        cap_type_styled = f"[{type_color}]{cap_type}[/{type_color}]"

        table.add_row(cap_id, cap_type_styled, title, timestamp)

    console.print(table)


# ─── Show Command ────────────────────────────────────────────────────


@main.command()
@click.argument("capture_id")
def show(capture_id: str):
    """🔍 Show details of a specific capture.

    CAPTURE_ID is the full or partial UUID of the capture.
    """
    cap = get_capture(capture_id)

    if cap is None:
        console.print(f"[red]✗ Capture not found: {capture_id}[/red]")
        raise SystemExit(1)

    # Pretty-print the full JSON
    console.print()
    console.print(f"[bold cyan]━━━ Capture {cap['id'][:8]} ━━━[/bold cyan]")
    console.print()

    # Header info
    console.print(f"  [bold]ID:[/bold]        {cap['id']}")
    console.print(f"  [bold]Type:[/bold]      {cap.get('type', '?')}")
    console.print(f"  [bold]Timestamp:[/bold] {cap.get('timestamp', '?')}")
    console.print(f"  [bold]Source:[/bold]    {cap.get('source', '?')}")

    # Metadata
    metadata = cap.get("metadata", {})
    if metadata:
        console.print()
        console.print("  [bold]Metadata:[/bold]")
        for key, value in metadata.items():
            console.print(f"    {key}: {value}")

    # Content
    content = cap.get("content", {})
    if content:
        console.print()
        console.print("  [bold]Content:[/bold]")

        if "url" in content:
            console.print(f"    [link={content['url']}]{content['url']}[/link]")

        if "file_path" in content:
            console.print(f"    File: {content['file_path']}")

        text = content.get("text", "")
        if text:
            console.print()
            # Show first 500 chars of text content
            preview = text[:500]
            if len(text) > 500:
                preview += f"\n    [dim]... ({len(text)} total chars)[/dim]"
            for line in preview.split("\n"):
                console.print(f"    {line}")

    console.print()
    console.print(f"[bold cyan]{'━' * 40}[/bold cyan]")

    # Also offer raw JSON view
    console.print()
    console.print("[dim]Raw JSON:[/dim]")
    console.print_json(json.dumps(cap, indent=2, ensure_ascii=False))


# ─── Process Command ─────────────────────────────────────────────────


@main.command()
@click.argument("capture_id", required=False, default=None)
@click.option(
    "--force", "-f", is_flag=True, default=False,
    help="Re-process captures that are already in the wiki.",
)
def process(capture_id: str | None, force: bool):
    """⚙️  Process raw captures: classify → embed → link → write wiki.

    With no argument, processes ALL unprocessed captures.
    Pass a CAPTURE_ID prefix to process a single capture.

    Use --force / -f to re-process captures already in the wiki.
    """
    # Lazy imports — heavy deps (sentence-transformers, chromadb) only load
    # when this command is actually called.
    from secondself.classify import classify_capture
    from secondself.config import WIKI_DIR
    from secondself.embed import EmbeddingEngine
    from secondself.linker import find_related, update_backlinks
    from secondself.wiki_writer import write_wiki_note

    # ── Resolve the capture list to work on ─────────────────────────────────
    all_captures = list_captures()
    if not all_captures:
        console.print("[yellow]⚠ No captures found in raw/. Run [bold]secondself capture note \"...\"[/bold] first.[/yellow]")
        return

    if capture_id:
        # Single-capture mode: prefix-match the provided ID
        target = get_capture(capture_id)
        if target is None:
            console.print(f"[red]✗ Capture not found: {capture_id}[/red]")
            raise SystemExit(1)
        queue = [target]
    else:
        queue = all_captures

    # ── Filter out already-processed unless --force ──────────────────────────
    if not force:
        unprocessed = [c for c in queue if not _is_processed(c["id"], WIKI_DIR)]
        skipped = len(queue) - len(unprocessed)
        if skipped:
            console.print(
                f"[dim]ℹ Skipping {skipped} already-processed capture(s). "
                "Use [bold]--force[/bold] to re-process.[/dim]"
            )
        queue = unprocessed

    if not queue:
        console.print("[green]✓ All captures are already processed. Nothing to do.[/green]")
        return

    # ── Initialise the embedding engine (loads model + ChromaDB) ────────────
    console.print()
    console.print("[bold cyan]⚙  Initialising embedding engine…[/bold cyan]")
    try:
        engine = EmbeddingEngine()
    except Exception as exc:
        console.print(f"[red]✗ Failed to initialise EmbeddingEngine: {exc}[/red]")
        raise SystemExit(1)

    # ── Process each capture ─────────────────────────────────────────────────
    total = len(queue)
    succeeded = 0
    failed = 0

    console.print(f"[bold]Processing {total} capture(s)…[/bold]\n")

    for idx, cap in enumerate(queue, start=1):
        cap_id = cap["id"]
        short_id = cap_id[:8]
        meta_title = cap.get("metadata", {}).get("title", short_id)

        console.print(
            f"[bold cyan][{idx}/{total}][/bold cyan] "
            f"[dim]{short_id}[/dim] · [white]{meta_title[:60]}[/white]"
        )

        try:
            # Step 1 — Classify
            console.print("  [dim]→ Classifying…[/dim]", end=" ")
            classification = classify_capture(cap)
            console.print(
                f"[green]{classification.category}[/green] "
                f"[dim](confidence {classification.confidence:.0%})[/dim]"
            )

            # Step 2 — Embed + store in ChromaDB
            console.print("  [dim]→ Embedding…[/dim]", end=" ")
            content_text = _get_content_text(cap)
            engine.store(
                capture_id=cap_id,
                text=content_text,
                metadata={
                    "title": classification.suggested_title or meta_title,
                    "category": classification.category,
                    "tags": json.dumps(classification.tags),
                    "timestamp": cap.get("timestamp", ""),
                },
            )
            console.print("[green]✓[/green]")

            # Step 3 — Find related notes
            console.print("  [dim]→ Finding related notes…[/dim]", end=" ")
            try:
                related = find_related(cap_id, engine)
            except ValueError:
                # Capture not in collection yet (edge case); treat as no related
                related = []
            console.print(f"[green]{len(related)} found[/green]")

            # Step 4 — Write wiki note
            console.print("  [dim]→ Writing wiki note…[/dim]", end=" ")
            wiki_path = write_wiki_note(cap, classification, related)
            console.print(f"[green]{wiki_path.relative_to(WIKI_DIR)}[/green]")

            # Step 5 — Update backlinks in related notes
            if related:
                console.print("  [dim]→ Updating backlinks…[/dim]", end=" ")
                update_backlinks(
                    wiki_dir=WIKI_DIR,
                    source_title=classification.suggested_title or meta_title,
                    related=related,
                )
                console.print("[green]✓[/green]")

            succeeded += 1

        except Exception as exc:
            console.print(f"\n  [red]✗ Failed: {exc}[/red]")
            failed += 1

        console.print()  # blank line between captures

    # ── Summary ──────────────────────────────────────────────────────────────
    console.print("─" * 50)
    console.print(
        f"[bold green]✓ {succeeded} processed[/bold green]"
        + (f"  [bold red]✗ {failed} failed[/bold red]" if failed else "")
    )


# ─── Reprocess Command ───────────────────────────────────────────────


@main.command()
@click.confirmation_option(
    prompt="This will delete all wiki notes and clear ChromaDB. Continue?"
)
def reprocess():
    """♻️  Re-classify and re-link ALL captures from scratch.

    ⚠ Destructive: clears wiki/ and ChromaDB before re-processing.
    """
    import shutil

    from secondself.config import CHROMA_DIR, PARA_CATEGORIES, WIKI_DIR
    from secondself.embed import COLLECTION_NAME

    # ── Step 1: Clear wiki/ subdirectories ──────────────────────────────────
    console.print("[yellow]Clearing wiki/ …[/yellow]")
    for category in PARA_CATEGORIES:
        cat_dir = WIKI_DIR / category
        if cat_dir.exists():
            shutil.rmtree(cat_dir)
            cat_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 2: Clear ChromaDB collection ───────────────────────────────────
    console.print("[yellow]Clearing ChromaDB collection…[/yellow]")
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )
        try:
            client.delete_collection(COLLECTION_NAME)
            console.print("[dim]  Collection deleted.[/dim]")
        except Exception:
            console.print("[dim]  Collection did not exist — nothing to delete.[/dim]")
    except Exception as exc:
        console.print(f"[red]✗ Could not clear ChromaDB: {exc}[/red]")
        raise SystemExit(1)

    # ── Step 3: Process everything (force=True implicit since wiki is empty) ─
    console.print()
    console.print("[bold]Re-processing all captures…[/bold]")
    ctx = click.get_current_context()
    ctx.invoke(process, capture_id=None, force=True)


# ─── Search Command ──────────────────────────────────────────────────


@main.command()
@click.argument("query")
@click.option(
    "--top-k", "-k", default=5, show_default=True,
    help="Number of results to return.",
)
def search(query: str, top_k: int):
    """🔍 Semantic search over your knowledge base.

    QUERY is the natural-language question or phrase to search for.
    """
    from secondself.embed import EmbeddingEngine

    console.print(f"\n[bold cyan]🔍 Searching for:[/bold cyan] {query}\n")

    try:
        engine = EmbeddingEngine()
    except Exception as exc:
        console.print(f"[red]✗ Failed to initialise EmbeddingEngine: {exc}[/red]")
        raise SystemExit(1)

    if engine.collection.count() == 0:
        console.print(
            "[yellow]⚠ Knowledge base is empty. "
            "Run [bold]secondself process[/bold] first.[/yellow]"
        )
        return

    results = engine.query_similar(query, k=top_k)

    if not results:
        console.print("[dim]No results found.[/dim]")
        return

    table = Table(
        title=f"Search Results for \"{query}\"",
        show_lines=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Score", style="bold green", width=7)
    table.add_column("Title", style="white", min_width=30)
    table.add_column("Category", style="magenta", width=10)
    table.add_column("Preview", style="dim", min_width=40)

    for rank, result in enumerate(results, start=1):
        score = result["similarity"]
        metadata = result.get("metadata", {})
        title = metadata.get("title", result["id"][:8])
        category = metadata.get("category", "—")
        # Short preview of the stored document text
        doc = result.get("document", "")
        preview = doc[:80].replace("\n", " ") + ("…" if len(doc) > 80 else "")

        # Colour-code the score
        if score >= 0.80:
            score_str = f"[green]{score:.3f}[/green]"
        elif score >= 0.65:
            score_str = f"[yellow]{score:.3f}[/yellow]"
        else:
            score_str = f"[red]{score:.3f}[/red]"

        table.add_row(str(rank), score_str, title, category, preview)

    console.print(table)
    console.print(
        f"\n[dim]Tip: Run [bold]secondself ask \"your question\"[/bold] "
        "to get a synthesised answer from your notes.[/dim]"
    )


# ─── Graph Command ───────────────────────────────────────────────────


@main.command()
def graph():
    """🗺️  Build the knowledge graph from wiki notes."""
    import json
    from secondself.config import WIKI_DIR, GRAPH_JSON
    from secondself.graph_builder import build_graph

    console.print(f"\n[bold cyan]🗺️  Building knowledge graph from {WIKI_DIR.name}/...[/bold cyan]")

    try:
        graph_data = build_graph(WIKI_DIR)

        # Write to JSON
        GRAPH_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(GRAPH_JSON, "w", encoding="utf-8") as f:
            json.dump(graph_data, f, indent=2)

        metadata = graph_data.get("metadata", {})
        nodes = metadata.get("total_nodes", 0)
        edges = metadata.get("total_edges", 0)
        categories = metadata.get("category_counts", {})

        console.print(f"[green]✓ Graph built successfully and saved to {GRAPH_JSON.name}[/green]")
        console.print(f"  [bold]Nodes:[/bold] {nodes}")
        console.print(f"  [bold]Edges:[/bold] {edges}")
        if categories:
            console.print("  [bold]Categories:[/bold]")
            for cat, count in categories.items():
                console.print(f"    - {cat}: {count}")
        console.print()

    except Exception as exc:
        console.print(f"[red]✗ Failed to build graph: {exc}[/red]")
        raise SystemExit(1)



# ─── Serve Command ────────────────────────────────────────────────────


@main.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, type=int, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload (dev mode).")
def serve(host: str, port: int, reload: bool):
    """🌐 Start the SecondSelf web server.

    Rebuilds the knowledge graph before launching, then serves the full
    web UI at http://<host>:<port>/
    """
    import uvicorn
    from secondself.config import GRAPH_JSON, WIKI_DIR
    from secondself.graph_builder import export_graph

    # Rebuild graph.json so the browser always gets fresh data on startup
    console.print("[dim]Rebuilding knowledge graph before starting server…[/dim]")
    try:
        export_graph(WIKI_DIR, GRAPH_JSON)
        console.print(f"[green]✓ Graph exported to {GRAPH_JSON.name}[/green]")
    except Exception as exc:
        console.print(f"[yellow]⚠ Could not rebuild graph: {exc}[/yellow]")

    console.print(f"\n[bold cyan]🌐 SecondSelf server starting at http://{host}:{port}[/bold cyan]\n")

    uvicorn.run(
        "secondself.server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


# ─── Ask Command ─────────────────────────────────────────────────────


@main.command("ask")
@click.argument("question")
def ask_cmd(question: str):
    """🔮 Ask a question about your knowledge base (RAG).

    QUESTION is the natural-language question to answer.
    """
    from secondself.ask import ask
    from secondself.embed import EmbeddingEngine

    console.print(f"\n[bold magenta]🔮 Asking:[/bold magenta] {question}\n")

    # Initialise embedding engine
    try:
        engine = EmbeddingEngine()
    except Exception as exc:
        console.print(f"[red]✗ Failed to initialise EmbeddingEngine: {exc}[/red]")
        raise SystemExit(1)

    if engine.collection.count() == 0:
        console.print(
            "[yellow]⚠ Knowledge base is empty. "
            "Run [bold]secondself process[/bold] first.[/yellow]"
        )
        return

    console.print("[dim]Retrieving relevant notes and generating answer…[/dim]\n")

    try:
        response = ask(question, engine)
    except Exception as exc:
        console.print(f"[red]✗ Failed to get answer: {exc}[/red]")
        raise SystemExit(1)

    # ── Print the answer ─────────────────────────────────────────────────
    confidence_colors = {"high": "green", "medium": "yellow", "low": "red"}
    conf_color = confidence_colors.get(response.confidence, "white")

    console.print(
        f"[bold cyan]━━━ Answer[/bold cyan] "
        f"[{conf_color}]({response.confidence} confidence)[/{conf_color}]\n"
    )
    console.print(response.answer)
    console.print()

    # ── Print source citations ───────────────────────────────────────────
    if response.sources:
        table = Table(
            title="📚 Sources",
            show_lines=False,
            header_style="bold cyan",
            border_style="dim",
        )
        table.add_column("#",          style="dim",          width=3)
        table.add_column("Score",      style="bold green",   width=7)
        table.add_column("Note Title", style="white",        min_width=30)
        table.add_column("Excerpt",    style="dim",          min_width=40)

        for rank, src in enumerate(response.sources, start=1):
            score = src.similarity
            if score >= 0.80:
                score_str = f"[green]{score:.3f}[/green]"
            elif score >= 0.65:
                score_str = f"[yellow]{score:.3f}[/yellow]"
            else:
                score_str = f"[red]{score:.3f}[/red]"

            excerpt = src.excerpt[:80].replace("\n", " ")
            if len(src.excerpt) > 80:
                excerpt += "…"

            table.add_row(str(rank), score_str, src.title, excerpt)

        console.print(table)
        console.print()

    # ── Print timing breakdown ───────────────────────────────────────────
    console.print(
        f"[dim]⏱  Embedding: {response.query_embedding_time_ms:.0f}ms  │  "
        f"Retrieval: {response.retrieval_time_ms:.0f}ms  │  "
        f"LLM: {response.llm_time_ms:.0f}ms[/dim]\n"
    )


# ─── Private helpers ─────────────────────────────────────────────────



def _is_processed(capture_id: str, wiki_dir) -> bool:
    """Return True if any wiki note's frontmatter contains this capture_id."""
    from pathlib import Path as _Path
    import re as _re

    wiki_dir = _Path(wiki_dir)
    for md_file in wiki_dir.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
        except OSError:
            continue
        fm_match = _re.match(r"^---\s*\n(.*?)\n---\s*\n", content, _re.DOTALL)
        if fm_match:
            for line in fm_match.group(1).splitlines():
                if line.strip().startswith("id:") and capture_id in line:
                    return True
    return False


def _get_content_text(capture: dict) -> str:
    """Extract embeddable text content from any capture type."""
    content = capture.get("content", {})
    cap_type = capture.get("type", "note")

    if cap_type == "url":
        url_val = content.get("url", "")
        text = content.get("text", "")
        return f"{url_val}\n\n{text}" if url_val else text

    if cap_type == "file":
        file_content = content.get("file_content", "")
        return file_content or content.get("file_path", "")

    return content.get("text", "")


if __name__ == "__main__":
    main()
