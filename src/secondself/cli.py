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


if __name__ == "__main__":
    main()
