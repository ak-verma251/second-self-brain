"""
Tests for the SecondSelf capture module.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

# Patch RAW_DIR before importing capture module
_test_raw_dir = Path(tempfile.mkdtemp()) / "raw"


@pytest.fixture(autouse=True)
def isolated_raw_dir(tmp_path):
    """Redirect RAW_DIR to a temporary directory for each test."""
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    with patch("secondself.capture.RAW_DIR", raw_dir):
        yield raw_dir


# ─── Test capture_note ───────────────────────────────────────────────


class TestCaptureNote:
    def test_creates_file(self, isolated_raw_dir):
        from secondself.capture import capture_note

        result = capture_note("Test note content")
        json_files = list(isolated_raw_dir.glob("*.json"))
        assert len(json_files) == 1

    def test_has_uuid(self, isolated_raw_dir):
        from secondself.capture import capture_note

        result = capture_note("Test note content")
        # UUID4 format: 8-4-4-4-12 hex chars
        import uuid

        parsed = uuid.UUID(result["id"])
        assert parsed.version == 4

    def test_has_timestamp(self, isolated_raw_dir):
        from secondself.capture import capture_note

        result = capture_note("Test note content")
        # Should be a valid ISO format timestamp
        ts = datetime.fromisoformat(result["timestamp"])
        assert ts.year >= 2024

    def test_correct_structure(self, isolated_raw_dir):
        from secondself.capture import capture_note

        result = capture_note("Hello world")
        assert result["type"] == "note"
        assert result["source"] == "cli"
        assert result["content"]["text"] == "Hello world"
        assert "title" in result["metadata"]
        assert result["metadata"]["word_count"] == 2
        assert result["metadata"]["char_count"] == 11

    def test_filename_format(self, isolated_raw_dir):
        from secondself.capture import capture_note

        result = capture_note("Test note")
        json_files = list(isolated_raw_dir.glob("*.json"))
        filename = json_files[0].name

        # Should match {YYYYMMDD}_{8-char-uuid}.json
        parts = filename.replace(".json", "").split("_", 1)
        assert len(parts) == 2
        assert len(parts[0]) == 8  # YYYYMMDD
        assert parts[0].isdigit()
        assert len(parts[1]) == 8  # first 8 chars of UUID

    def test_auto_title_short_text(self, isolated_raw_dir):
        from secondself.capture import capture_note

        result = capture_note("Short note")
        assert result["metadata"]["title"] == "Short note"

    def test_auto_title_long_text(self, isolated_raw_dir):
        from secondself.capture import capture_note

        long_text = " ".join(f"word{i}" for i in range(20))
        result = capture_note(long_text)
        # Should truncate to ~10 words
        assert result["metadata"]["title"].endswith("...")

    def test_json_is_readable(self, isolated_raw_dir):
        from secondself.capture import capture_note

        capture_note("Readable JSON test")
        json_files = list(isolated_raw_dir.glob("*.json"))
        content = json_files[0].read_text(encoding="utf-8")
        data = json.loads(content)
        assert data["content"]["text"] == "Readable JSON test"
        # Should be indented (pretty-printed)
        assert "\n" in content


# ─── Test capture_url ────────────────────────────────────────────────


class TestCaptureUrl:
    def test_captures_url_with_fetch(self, isolated_raw_dir):
        from secondself.capture import capture_url

        # Mock httpx to avoid real network calls
        mock_html = '<html><head><title>Test Page</title><meta name="description" content="A test page"></head></html>'

        with patch("secondself.capture.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value.text = mock_html

            result = capture_url("https://example.com")

        assert result["type"] == "url"
        assert result["content"]["url"] == "https://example.com"
        assert "Test Page" in result["metadata"]["title"]

    def test_handles_fetch_failure(self, isolated_raw_dir):
        from secondself.capture import capture_url

        with patch("secondself.capture.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.side_effect = Exception("Connection refused")

            result = capture_url("https://nonexistent.example.com")

        # Should still create a capture with the URL even if fetch fails
        assert result["type"] == "url"
        assert result["content"]["url"] == "https://nonexistent.example.com"
        assert result["metadata"]["fetch_failed"] is True

    def test_url_capture_creates_file(self, isolated_raw_dir):
        from secondself.capture import capture_url

        with patch("secondself.capture.httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.get.return_value.text = "<html><title>Test</title></html>"

            capture_url("https://example.com")

        json_files = list(isolated_raw_dir.glob("*.json"))
        assert len(json_files) == 1


# ─── Test capture_file ───────────────────────────────────────────────


class TestCaptureFile:
    def test_captures_text_file(self, isolated_raw_dir, tmp_path):
        from secondself.capture import capture_file

        # Create a test text file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello from a text file!", encoding="utf-8")

        result = capture_file(str(test_file))

        assert result["type"] == "file"
        assert "Hello from a text file!" in result["content"]["file_content"]
        assert result["metadata"]["extraction_method"] == "text"

    def test_captures_markdown_file(self, isolated_raw_dir, tmp_path):
        from secondself.capture import capture_file

        test_file = tmp_path / "notes.md"
        test_file.write_text("# My Notes\n\nSome content here.", encoding="utf-8")

        result = capture_file(str(test_file))

        assert result["type"] == "file"
        assert "# My Notes" in result["content"]["file_content"]

    def test_handles_binary_file(self, isolated_raw_dir, tmp_path):
        from secondself.capture import capture_file

        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        result = capture_file(str(test_file))

        assert result["type"] == "file"
        assert result["metadata"]["extraction_method"] == "binary"

    def test_file_not_found_raises(self, isolated_raw_dir):
        from secondself.capture import capture_file

        with pytest.raises(FileNotFoundError):
            capture_file("/nonexistent/path/file.txt")

    def test_captures_python_file(self, isolated_raw_dir, tmp_path):
        from secondself.capture import capture_file

        test_file = tmp_path / "script.py"
        test_file.write_text('print("hello world")', encoding="utf-8")

        result = capture_file(str(test_file))

        assert result["type"] == "file"
        assert 'print("hello world")' in result["content"]["file_content"]
        assert result["metadata"]["file_extension"] == ".py"


# ─── Test list_captures ──────────────────────────────────────────────


class TestListCaptures:
    def test_returns_all_captures(self, isolated_raw_dir):
        from secondself.capture import capture_note, list_captures

        capture_note("First note")
        capture_note("Second note")
        capture_note("Third note")

        result = list_captures()
        assert len(result) == 3

    def test_sorted_by_timestamp(self, isolated_raw_dir):
        from secondself.capture import capture_note, list_captures

        capture_note("First")
        capture_note("Second")
        capture_note("Third")

        result = list_captures()
        # Should be sorted newest first
        timestamps = [c["timestamp"] for c in result]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_empty_list(self, isolated_raw_dir):
        from secondself.capture import list_captures

        result = list_captures()
        assert result == []


# ─── Test get_capture ────────────────────────────────────────────────


class TestGetCapture:
    def test_get_by_full_id(self, isolated_raw_dir):
        from secondself.capture import capture_note, get_capture

        cap = capture_note("Findable note")
        found = get_capture(cap["id"])
        assert found is not None
        assert found["id"] == cap["id"]

    def test_get_by_prefix(self, isolated_raw_dir):
        from secondself.capture import capture_note, get_capture

        cap = capture_note("Prefix match note")
        found = get_capture(cap["id"][:8])
        assert found is not None
        assert found["id"] == cap["id"]

    def test_not_found_returns_none(self, isolated_raw_dir):
        from secondself.capture import get_capture

        found = get_capture("nonexistent-id")
        assert found is None


# ─── Test immutability ───────────────────────────────────────────────


class TestImmutability:
    def test_files_not_modified_after_creation(self, isolated_raw_dir):
        from secondself.capture import capture_note

        capture_note("Immutable note")

        json_files = list(isolated_raw_dir.glob("*.json"))
        assert len(json_files) == 1

        # Read the file content and modification time
        original_content = json_files[0].read_text(encoding="utf-8")
        original_mtime = json_files[0].stat().st_mtime

        # Capture another note — should NOT modify the first file
        capture_note("Another note")

        # Original file should be unchanged
        assert json_files[0].read_text(encoding="utf-8") == original_content
        assert json_files[0].stat().st_mtime == original_mtime
