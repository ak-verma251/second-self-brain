"""
SecondSelf — Capture Module

Core capture logic for notes, URLs, and files.
Every capture is stored as an immutable JSON file in raw/.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pymupdf
from rich.console import Console

from secondself.config import RAW_DIR

console = Console()

# File extensions that can be read as plain text
TEXT_EXTENSIONS = {
    ".txt", ".md", ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".sh",
    ".bash", ".zsh", ".fish", ".bat", ".ps1", ".rb", ".go", ".rs",
    ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".swift", ".kt",
    ".r", ".R", ".sql", ".xml", ".csv", ".log", ".env", ".gitignore",
    ".dockerfile", ".makefile",
}


def _generate_id() -> str:
    """Generate a new UUID4 string."""
    return str(uuid.uuid4())


def _timestamp_now() -> str:
    """Generate an ISO 8601 timestamp with timezone."""
    return datetime.now(timezone.utc).astimezone().isoformat()


def _build_filename(capture_id: str, timestamp: str) -> str:
    """Build filename: {YYYYMMDD}_{first-8-chars-of-uuid}.json"""
    # Parse the date from the ISO timestamp
    dt = datetime.fromisoformat(timestamp)
    date_str = dt.strftime("%Y%m%d")
    short_id = capture_id[:8]
    return f"{date_str}_{short_id}.json"


def _auto_title(text: str, max_words: int = 10) -> str:
    """Generate a title from the first N words of text."""
    words = text.split()[:max_words]
    title = " ".join(words)
    if len(text.split()) > max_words:
        title += "..."
    return title


def _write_capture(capture: dict) -> Path:
    """Write a capture dict to raw/ as JSON. Returns the file path."""
    filename = _build_filename(capture["id"], capture["timestamp"])
    filepath = RAW_DIR / filename
    filepath.write_text(json.dumps(capture, indent=2, ensure_ascii=False), encoding="utf-8")
    return filepath


def capture_note(text: str) -> dict:
    """Capture a plain text note.

    Args:
        text: The note text to capture.

    Returns:
        The capture dict that was written to disk.
    """
    capture_id = _generate_id()
    timestamp = _timestamp_now()

    capture = {
        "id": capture_id,
        "timestamp": timestamp,
        "type": "note",
        "source": "cli",
        "content": {
            "text": text,
        },
        "metadata": {
            "title": _auto_title(text),
            "word_count": len(text.split()),
            "char_count": len(text),
        },
    }

    filepath = _write_capture(capture)
    console.print(f"[green]✓[/green] Captured note: [bold]{capture_id[:8]}[/bold] — {capture['metadata']['title']}")
    console.print(f"  [dim]→ {filepath.name}[/dim]")

    return capture


def capture_url(url: str) -> dict:
    """Capture a URL with fetched title and description.

    Args:
        url: The URL to capture.

    Returns:
        The capture dict that was written to disk.
    """
    capture_id = _generate_id()
    timestamp = _timestamp_now()

    # Try to fetch page title and meta description
    title = url  # Fallback title
    description = ""
    fetch_failed = False

    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "SecondSelf/0.1"})
            html = response.text

            # Extract <title>
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            if title_match:
                title = title_match.group(1).strip()
                # Clean up HTML entities
                title = title.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                title = title.replace("&#39;", "'").replace("&quot;", '"')

            # Extract <meta name="description">
            desc_match = re.search(
                r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
                html,
                re.IGNORECASE | re.DOTALL,
            )
            if desc_match:
                description = desc_match.group(1).strip()

    except Exception as e:
        fetch_failed = True
        console.print(f"  [yellow]⚠ Could not fetch URL: {e}[/yellow]")

    # Build text content from title + description
    text_content = title
    if description:
        text_content = f"{title}\n\n{description}"

    capture = {
        "id": capture_id,
        "timestamp": timestamp,
        "type": "url",
        "source": "cli",
        "content": {
            "text": text_content,
            "url": url,
        },
        "metadata": {
            "title": title,
            "word_count": len(text_content.split()),
            "char_count": len(text_content),
            "fetch_failed": fetch_failed,
        },
    }

    filepath = _write_capture(capture)
    console.print(f"[green]✓[/green] Captured URL: [bold]{capture_id[:8]}[/bold] — {title}")
    console.print(f"  [dim]→ {filepath.name}[/dim]")

    return capture


def capture_file(file_path: str) -> dict:
    """Capture a file with extracted text content.

    Args:
        file_path: Path to the file to capture.

    Returns:
        The capture dict that was written to disk.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    capture_id = _generate_id()
    timestamp = _timestamp_now()

    file_content = ""
    extraction_method = "none"

    suffix = path.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        # Read text files directly
        try:
            file_content = path.read_text(encoding="utf-8")
            extraction_method = "text"
        except UnicodeDecodeError:
            try:
                file_content = path.read_text(encoding="latin-1")
                extraction_method = "text-latin1"
            except Exception:
                file_content = f"[Could not read text from {path.name}]"
                extraction_method = "failed"

    elif suffix == ".pdf":
        # Extract text from PDF using pymupdf
        try:
            doc = pymupdf.open(str(path))
            pages = []
            # Limit to first 50 pages for large PDFs
            max_pages = min(len(doc), 50)
            for page_num in range(max_pages):
                page_text = doc[page_num].get_text()
                if page_text.strip():
                    pages.append(page_text)
            doc.close()

            file_content = "\n\n".join(pages)
            extraction_method = "pdf"
            if len(doc) > 50:
                file_content += f"\n\n[... truncated, showing {max_pages} of {len(doc)} pages]"
        except Exception as e:
            file_content = f"[PDF extraction failed: {e}]"
            extraction_method = "failed"

    else:
        # Binary or unsupported file
        file_content = f"[Binary file: {path.name} ({path.stat().st_size} bytes)]"
        extraction_method = "binary"

    # Auto-generate title from filename
    title = path.stem.replace("-", " ").replace("_", " ").title()

    capture = {
        "id": capture_id,
        "timestamp": timestamp,
        "type": "file",
        "source": "cli",
        "content": {
            "text": file_content[:500] if file_content else path.name,
            "file_path": str(path),
            "file_content": file_content,
        },
        "metadata": {
            "title": title,
            "word_count": len(file_content.split()),
            "char_count": len(file_content),
            "original_filename": path.name,
            "file_extension": suffix,
            "extraction_method": extraction_method,
        },
    }

    filepath = _write_capture(capture)
    console.print(f"[green]✓[/green] Captured file: [bold]{capture_id[:8]}[/bold] — {path.name}")
    console.print(f"  [dim]→ {filepath.name} ({extraction_method})[/dim]")

    return capture


def list_captures() -> list[dict]:
    """List all captures in raw/, sorted by timestamp (newest first).

    Returns:
        List of capture dicts, sorted by timestamp descending.
    """
    captures = []

    for json_file in sorted(RAW_DIR.glob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            captures.append(data)
        except (json.JSONDecodeError, OSError) as e:
            console.print(f"[yellow]⚠ Skipping {json_file.name}: {e}[/yellow]")

    # Sort by timestamp descending (newest first)
    captures.sort(key=lambda c: c.get("timestamp", ""), reverse=True)
    return captures


def get_capture(capture_id: str) -> dict | None:
    """Retrieve a specific capture by ID (supports prefix match).

    Args:
        capture_id: Full or partial (prefix) UUID of the capture.

    Returns:
        The capture dict, or None if not found.
    """
    for json_file in RAW_DIR.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            if data.get("id", "").startswith(capture_id):
                return data
        except (json.JSONDecodeError, OSError):
            continue

    return None
