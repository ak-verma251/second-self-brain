"""
SecondSelf — Streamlit App (Redesigned to match web/ frontend)

Uses streamlit.components.v1.html() for the vis-network graph and note panel,
with Streamlit native widgets for capture, ask, and answer display.
All CSS ported from web/style.css (glassmorphism, animations, responsive).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# ── Ensure Streamlit secrets are available as env vars ────────────────────────
try:
    if "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except FileNotFoundError:
    pass

# ── Import SecondSelf modules ─────────────────────────────────────────────────
from secondself.config import (
    WIKI_DIR, RAW_DIR, DATA_DIR, GRAPH_JSON,
    PARA_CATEGORIES, CHROMA_DIR,
)
from secondself.graph_builder import build_graph, export_graph
from secondself.embed import EmbeddingEngine
from secondself.capture import capture_note, capture_url
from secondself.classify import classify_capture
from secondself.linker import find_related, update_backlinks
from secondself.wiki_writer import write_wiki_note

# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS & CACHE
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_COLORS = {
    "projects":  "#6C5CE7",
    "areas":     "#00B894",
    "resources": "#0984E3",
    "archives":  "#636E72",
}

@st.cache_resource(show_spinner="Loading AI models…")
def get_engine() -> EmbeddingEngine:
    engine = EmbeddingEngine()
    _auto_populate_chroma(engine)
    return engine

def _auto_populate_chroma(engine: EmbeddingEngine) -> None:
    if engine.collection.count() > 0: return
    if not WIKI_DIR.exists(): return
    md_files = list(WIKI_DIR.rglob("*.md"))
    for md_file in md_files:
        try:
            raw = md_file.read_text(encoding="utf-8")
        except OSError: continue
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not fm_match: continue
        fm_data = {}
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm_data[k.strip()] = v.strip().strip('"').strip("'")
        note_id = fm_data.get("id", md_file.stem)
        title = fm_data.get("title", md_file.stem)
        category = fm_data.get("category", "resources")
        tags_str = fm_data.get("tags", "[]")
        body = raw[fm_match.end():]
        text_lines = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith(("#", ">"))]
        text = "\n".join(text_lines).strip() or title
        try:
            engine.store(
                capture_id=note_id, text=text,
                metadata={"title": title, "category": category, "tags": tags_str, "timestamp": fm_data.get("created", "")}
            )
        except Exception: pass

def _get_graph_data() -> dict:
    if not WIKI_DIR.exists(): return {"nodes": [], "edges": [], "metadata": {}}
    md_files = list(WIKI_DIR.rglob("*.md"))
    if not md_files: return {"nodes": [], "edges": [], "metadata": {}}
    newest = max(f.stat().st_mtime for f in md_files)
    if GRAPH_JSON.exists() and GRAPH_JSON.stat().st_mtime >= newest:
        try:
            with open(GRAPH_JSON, encoding="utf-8") as f: return json.load(f)
        except: pass
    gd = build_graph(WIKI_DIR)
    try: export_graph(WIKI_DIR, GRAPH_JSON)
    except: pass
    return gd

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="ASHISH'S BRaIN",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ═══════════════════════════════════════════════════════════════════════════════
#  CSS — Full design system ported from web/style.css
# ═══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* ── Design Tokens ─────────────────────────────────────────── */
    :root {
      --bg-primary:       #0a0a1a;
      --bg-secondary:     #12122a;
      --bg-tertiary:      #1a1a35;
      --bg-glass:         rgba(255, 255, 255, 0.05);
      --bg-glass-hover:   rgba(255, 255, 255, 0.08);
      --text-primary:     #e2e8f0;
      --text-secondary:   #94a3b8;
      --text-muted:       #475569;
      --accent-projects:  #6C5CE7;
      --accent-areas:     #00B894;
      --accent-resources: #0984E3;
      --accent-archives:  #636E72;
      --accent-glow:      rgba(108, 92, 231, 0.3);
      --border-glass:     rgba(255, 255, 255, 0.08);
      --border-glow:      rgba(108, 92, 231, 0.4);
      --font-family:      'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      --radius-sm:        6px;
      --radius-md:        12px;
      --radius-lg:        18px;
      --transition:       200ms ease;
    }

    /* ── Reset Streamlit defaults ──────────────────────────────── */
    html, body, [class*="css"] { font-family: var(--font-family) !important; }

    .stApp {
        background-color: var(--bg-primary) !important;
        background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.04) 1px, transparent 0);
        background-size: 28px 28px;
        color: var(--text-primary);
    }

    header[data-testid="stHeader"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    [data-testid="stBottomBlockContainer"] { background: transparent !important; }

    /* Custom scrollbar */
    ::-webkit-scrollbar { width: 5px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: var(--border-glass); border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.15); }

    /* ── App Header ────────────────────────────────────────────── */
    .app-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 24px;
        background: rgba(10, 10, 26, 0.8);
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border-bottom: 1px solid var(--border-glass);
        box-shadow: 0 4px 24px rgba(0,0,0,0.35);
        margin: -1rem -1rem 0 -1rem;
    }

    .logo {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 18px;
        font-weight: 700;
        letter-spacing: -0.5px;
        color: var(--text-primary);
        user-select: none;
    }

    .logo-icon {
        font-size: 22px;
        filter: drop-shadow(0 0 8px rgba(108, 92, 231, 0.6));
        animation: breathe 4s ease-in-out infinite;
    }

    @keyframes breathe {
        0%, 100% { filter: drop-shadow(0 0 8px rgba(108, 92, 231, 0.6)); }
        50%       { filter: drop-shadow(0 0 18px rgba(108, 92, 231, 1)); }
    }

    .header-nav {
        display: flex;
        align-items: center;
        gap: 12px;
    }

    .stats-pill {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 5px 14px;
        border-radius: 20px;
        background: var(--bg-glass);
        border: 1px solid var(--border-glass);
        font-size: 12px;
        color: var(--text-muted);
        user-select: none;
    }

    .stats-icon { font-size: 10px; opacity: .6; }
    .stats-divider { opacity: .3; }

    /* ── Capture Button (Streamlit override) ────────────────────── */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #6C5CE7, #a78bfa) !important;
        border: none !important;
        box-shadow: 0 0 18px rgba(108, 92, 231, 0.25) !important;
        color: white !important;
        font-weight: 600 !important;
        border-radius: var(--radius-sm) !important;
        transition: all var(--transition) !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        box-shadow: 0 0 28px rgba(108, 92, 231, 0.45) !important;
        transform: translateY(-1px);
    }

    /* ── Chat Input (Rainbow border) ───────────────────────────── */
    @property --rainbow-angle {
        syntax: "<angle>";
        initial-value: 0deg;
        inherits: false;
    }
    @keyframes rainbowSpin {
        to { --rainbow-angle: 360deg; }
    }

    [data-testid="stChatInput"] {
        background: transparent !important;
    }
    [data-testid="stChatInput"] > div {
        border-radius: var(--radius-md) !important;
        border: 2px solid var(--border-glass) !important;
        background: var(--bg-glass) !important;
        transition: border-color 0.3s ease, background 0.3s ease, box-shadow 0.3s ease !important;
    }
    [data-testid="stChatInput"] > div:focus-within {
        border-color: transparent !important;
        background:
            linear-gradient(var(--bg-glass-hover), var(--bg-glass-hover)) padding-box,
            conic-gradient(
                from var(--rainbow-angle),
                #ff0000, #ff8800, #ffff00, #00ff00,
                #00ccff, #0044ff, #8800ff, #ff0088, #ff0000
            ) border-box !important;
        animation: rainbowSpin 2.5s linear infinite !important;
        box-shadow:
            0 0 8px rgba(255, 0, 128, 0.45),
            0 0 18px rgba(0, 200, 255, 0.35),
            0 0 30px rgba(136, 0, 255, 0.25) !important;
    }
    [data-testid="stChatInput"] textarea {
        color: var(--text-primary) !important;
        font-family: var(--font-family) !important;
    }
    [data-testid="stChatInput"] textarea::placeholder {
        color: var(--text-muted) !important;
    }

    /* ── Answer Glass Card ─────────────────────────────────────── */
    .answer-card {
        background: rgba(255,255,255,0.03);
        backdrop-filter: blur(12px);
        border: 1px solid var(--border-glass);
        border-radius: var(--radius-md);
        padding: 16px 20px;
        margin-bottom: 12px;
        animation: slideUp 250ms ease;
    }
    @keyframes slideUp {
        from { opacity: 0; transform: translateY(8px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .answer-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 8px;
        padding-bottom: 6px;
        border-bottom: 1px solid var(--border-glass);
    }
    .answer-question {
        font-style: italic;
        color: var(--text-muted);
        font-size: 11px;
        flex: 1;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .answer-meta {
        display: flex;
        align-items: center;
        gap: 10px;
        flex-shrink: 0;
    }
    .conf-badge {
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }
    .timing-info {
        font-size: 11px;
        color: var(--text-muted);
    }
    .answer-body {
        line-height: 1.65;
        color: var(--text-primary);
        font-size: 14px;
    }
    .answer-body p { margin: 0 0 6px; }
    .answer-body code {
        background: rgba(255,255,255,0.07);
        padding: 1px 5px;
        border-radius: 4px;
        font-size: 12px;
    }
    .inline-citation {
        color: #a78bfa;
        font-size: 11px;
        font-weight: 500;
        background: rgba(108, 92, 231, 0.12);
        padding: 1px 6px;
        border-radius: 4px;
        white-space: nowrap;
    }
    .answer-sources {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 5px;
        margin-top: 10px;
        padding-top: 7px;
        border-top: 1px solid var(--border-glass);
    }
    .sources-label {
        font-size: 10px;
        font-weight: 600;
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .source-chip {
        display: inline-flex;
        align-items: center;
        padding: 2px 9px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 500;
        cursor: default;
        background: rgba(108, 92, 231, 0.14);
        color: #a78bfa;
        border: 1px solid rgba(108, 92, 231, 0.28);
        transition: all var(--transition);
    }
    .source-chip:hover {
        background: rgba(108, 92, 231, 0.26);
        border-color: rgba(108, 92, 231, 0.5);
    }

    /* ── Dialog (capture modal) styling ─────────────────────────── */
    [data-testid="stDialog"] {
        background: var(--bg-secondary) !important;
    }
    div[role="dialog"] {
        background: var(--bg-secondary) !important;
        border: 1px solid var(--border-glass) !important;
        border-radius: var(--radius-lg) !important;
        box-shadow: 0 24px 80px rgba(0,0,0,0.6), 0 0 60px rgba(108,92,231,0.07) !important;
    }
    div[role="dialog"] [data-testid="stTextArea"] textarea {
        background: var(--bg-glass) !important;
        border: 1px solid var(--border-glass) !important;
        border-radius: var(--radius-md) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-family) !important;
    }
    div[role="dialog"] [data-testid="stTextArea"] textarea:focus {
        border-color: var(--border-glow) !important;
        box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.1) !important;
    }
    div[role="dialog"] [data-testid="stTextInput"] input {
        background: var(--bg-glass) !important;
        border: 1px solid var(--border-glass) !important;
        border-radius: var(--radius-md) !important;
        color: var(--text-primary) !important;
        font-family: var(--font-family) !important;
    }
    div[role="dialog"] [data-testid="stTextInput"] input:focus {
        border-color: var(--border-glow) !important;
        box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.1) !important;
    }

    /* ── Tabs styling ──────────────────────────────────────────── */
    [data-testid="stTabs"] button {
        font-family: var(--font-family) !important;
        font-weight: 500 !important;
        color: var(--text-muted) !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--text-primary) !important;
        border-bottom-color: var(--accent-projects) !important;
    }

    /* ── Spinner / toast ───────────────────────────────────────── */
    .stSpinner > div { color: #a78bfa !important; }

    /* ── Remove extra padding ──────────────────────────────────── */
    .block-container { padding-top: 0 !important; padding-bottom: 0 !important; }

    /* ── File uploader styling ─────────────────────────────────── */
    [data-testid="stFileUploader"] {
        border: 1px dashed var(--border-glass) !important;
        border-radius: var(--radius-md) !important;
    }

    /* ── Responsive ────────────────────────────────────────────── */
    @media (max-width: 900px) {
        .stats-pill { display: none !important; }
    }
    @media (max-width: 680px) {
        .logo-text { display: none !important; }
    }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  CAPTURE MODAL
# ═══════════════════════════════════════════════════════════════════════════════

@st.dialog("✦ Capture Knowledge")
def capture_modal():
    tab1, tab2, tab3 = st.tabs(["📝 Note", "🔗 URL", "📄 File"])

    with tab1:
        note_text = st.text_area("Your note", height=150, placeholder="Type or paste your note here…", label_visibility="collapsed")
        if st.button("Capture Note", use_container_width=True, type="primary", key="cap_note"):
            if note_text.strip():
                with st.spinner("Processing…"):
                    try:
                        capture = capture_note(note_text.strip())
                        classification = classify_capture(capture)
                        engine = get_engine()
                        engine.store(
                            capture_id=capture["id"],
                            text=capture.get("content", {}).get("text", ""),
                            metadata={
                                "title": classification.suggested_title,
                                "category": classification.category,
                                "tags": json.dumps(classification.tags),
                                "timestamp": capture.get("timestamp", ""),
                            },
                        )
                        related = []
                        try: related = find_related(capture["id"], engine)
                        except Exception: pass
                        write_wiki_note(capture, classification, related)
                        if related: update_backlinks(WIKI_DIR, classification.suggested_title, related)
                        if GRAPH_JSON.exists(): GRAPH_JSON.unlink()
                        st.success(f"Captured: {classification.suggested_title}")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab2:
        url_input = st.text_input("URL", placeholder="https://…", label_visibility="collapsed")
        if st.button("Capture URL", use_container_width=True, type="primary", key="cap_url"):
            if url_input.strip():
                with st.spinner("Processing…"):
                    try:
                        capture = capture_url(url_input.strip())
                        classification = classify_capture(capture)
                        engine = get_engine()
                        content_text = f"{capture.get('content', {}).get('url', '')}\n\n{capture.get('content', {}).get('text', '')}"
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
                        related = []
                        try: related = find_related(capture["id"], engine)
                        except Exception: pass
                        write_wiki_note(capture, classification, related)
                        if related: update_backlinks(WIKI_DIR, classification.suggested_title, related)
                        if GRAPH_JSON.exists(): GRAPH_JSON.unlink()
                        st.success(f"Captured: {classification.suggested_title}")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    with tab3:
        uploaded = st.file_uploader("Upload a file", type=["txt", "md", "pdf", "csv", "json", "py", "js"], label_visibility="collapsed")
        if uploaded and st.button("Capture File", use_container_width=True, type="primary", key="cap_file"):
            with st.spinner("Processing…"):
                try:
                    import tempfile
                    with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{uploaded.name}") as tmp:
                        tmp.write(uploaded.read())
                        tmp_path = tmp.name
                    from secondself.capture import capture_file
                    capture = capture_file(tmp_path)
                    classification = classify_capture(capture)
                    engine = get_engine()
                    engine.store(
                        capture_id=capture["id"],
                        text=capture.get("content", {}).get("text", ""),
                        metadata={
                            "title": classification.suggested_title,
                            "category": classification.category,
                            "tags": json.dumps(classification.tags),
                            "timestamp": capture.get("timestamp", ""),
                        },
                    )
                    related = []
                    try: related = find_related(capture["id"], engine)
                    except Exception: pass
                    write_wiki_note(capture, classification, related)
                    if related: update_backlinks(WIKI_DIR, classification.suggested_title, related)
                    if GRAPH_JSON.exists(): GRAPH_JSON.unlink()
                    os.unlink(tmp_path)
                    st.success(f"Captured: {classification.suggested_title}")
                    time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
#  BUILD GRAPH HTML COMPONENT
# ═══════════════════════════════════════════════════════════════════════════════

def _build_graph_html(graph_data: dict, wiki_count: int, embedded_count: int) -> str:
    """Build a self-contained HTML page with vis-network graph, note panel,
    stats dashboard, category filters, and all interactions."""

    nodes_json = json.dumps(graph_data.get("nodes", []))
    edges_json = json.dumps(graph_data.get("edges", []))
    meta_json  = json.dumps(graph_data.get("metadata", {}))

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
/* ── Design Tokens ─────────────────────────────────────────── */
:root {{
  --bg-primary:       #0a0a1a;
  --bg-secondary:     #12122a;
  --bg-tertiary:      #1a1a35;
  --bg-glass:         rgba(255, 255, 255, 0.05);
  --bg-glass-hover:   rgba(255, 255, 255, 0.08);
  --text-primary:     #e2e8f0;
  --text-secondary:   #94a3b8;
  --text-muted:       #475569;
  --accent-projects:  #6C5CE7;
  --accent-areas:     #00B894;
  --accent-resources: #0984E3;
  --accent-archives:  #636E72;
  --border-glass:     rgba(255, 255, 255, 0.08);
  --border-glow:      rgba(108, 92, 231, 0.4);
  --font-family:      'Inter', -apple-system, sans-serif;
  --radius-sm:        6px;
  --radius-md:        12px;
  --transition:       200ms ease;
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
html, body {{ height: 100%; overflow: hidden; font-family: var(--font-family); background: var(--bg-primary); color: var(--text-primary); font-size: 14px; line-height: 1.6; }}

::-webkit-scrollbar {{ width: 5px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: var(--border-glass); border-radius: 4px; }}

/* ── Layout ──────────────────────────────────────────────────── */
#main-content {{
  height: 100%;
  display: grid;
  grid-template-columns: 1fr 340px;
}}

/* ── Graph Section ───────────────────────────────────────────── */
#graph-section {{
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-right: 1px solid var(--border-glass);
}}

.graph-filters {{
  display: flex;
  align-items: center;
  padding: 8px 14px;
  background: rgba(18, 18, 42, 0.7);
  border-bottom: 1px solid var(--border-glass);
  backdrop-filter: blur(12px);
  gap: 8px;
  flex-shrink: 0;
}}
.graph-filters span {{ color: var(--text-muted); font-size: 12px; font-weight: 500; margin-right: 4px; }}

.filter-btn {{
  background: var(--bg-glass);
  border: 1px solid var(--border-glass);
  color: var(--text-secondary);
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--transition);
  font-family: var(--font-family);
}}
.filter-btn:hover {{ background: var(--bg-glass-hover); color: var(--text-primary); }}
.filter-btn.active {{ background: rgba(108, 92, 231, 0.2); color: #a78bfa; border-color: rgba(108, 92, 231, 0.4); }}

#graph-container {{
  flex: 1;
  position: relative;
  background: var(--bg-primary);
  overflow: hidden;
}}

/* Graph meta badge */
.graph-meta-badge {{
  position: absolute;
  top: 10px; left: 10px;
  z-index: 10;
  display: flex;
  gap: 6px;
  pointer-events: none;
}}
.graph-meta-pill {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 9px;
  border-radius: 20px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(10, 10, 26, 0.8);
  border: 1px solid rgba(255,255,255,.07);
  color: var(--pill-color, #94a3b8);
  backdrop-filter: blur(8px);
}}
.graph-meta-pill strong {{ color: #e2e8f0; font-weight: 700; }}

/* Empty state */
#graph-empty-state {{
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 40px;
  text-align: center;
  background: radial-gradient(ellipse at center, rgba(108,92,231,0.05) 0%, transparent 70%);
  z-index: 5;
}}
#graph-empty-state.hidden {{ display: none; }}
.empty-state-icon {{
  font-size: 52px;
  filter: drop-shadow(0 0 20px rgba(108,92,231,0.4));
  animation: float 3s ease-in-out infinite;
}}
@keyframes float {{
  0%, 100% {{ transform: translateY(0); }}
  50%      {{ transform: translateY(-8px); }}
}}
.empty-state-heading {{ font-size: 22px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.5px; }}
.empty-state-body {{ font-size: 14px; color: var(--text-secondary); line-height: 1.7; max-width: 340px; }}

/* Stats bar */
.stats-bar {{
  height: 46px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  background: rgba(18, 18, 42, 0.7);
  border-top: 1px solid var(--border-glass);
  backdrop-filter: blur(12px);
  padding: 0 14px;
}}
.stats-bar-inner {{
  display: flex;
  gap: 4px;
  width: 100%;
}}
.stat-card {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  background: var(--bg-glass);
  border: 1px solid var(--border-glass);
  position: relative;
  min-width: 56px;
  transition: background var(--transition);
}}
.stat-card:hover {{ background: var(--bg-glass-hover); }}
.stat-card-count {{ font-size: 16px; font-weight: 700; color: var(--text-primary); line-height: 1.1; letter-spacing: -0.5px; }}
.stat-card-label {{ font-size: 9px; font-weight: 500; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.6px; }}
.stat-card-dot {{
  position: absolute;
  top: 5px; right: 6px;
  width: 5px; height: 5px;
  border-radius: 50%;
  opacity: 0.7;
}}
.stat-card-total .stat-card-count {{ color: #a78bfa; }}

/* ── Note Panel ──────────────────────────────────────────────── */
#note-panel {{
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-secondary);
}}
#note-panel-content {{
  flex: 1;
  overflow-y: auto;
  padding: 0;
  position: relative;
}}

.note-panel-empty {{
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 32px;
  text-align: center;
  pointer-events: none;
}}
.note-panel-empty-icon {{ font-size: 32px; color: var(--text-muted); opacity: 0.4; }}
.note-panel-empty-text {{ font-size: 13px; color: var(--text-muted); line-height: 1.7; }}

@keyframes panelSlideIn {{
  from {{ opacity: 0; transform: translateX(14px); }}
  to   {{ opacity: 1; transform: translateX(0); }}
}}
.panel-enter {{ animation: panelSlideIn 220ms cubic-bezier(0.25, 0.46, 0.45, 0.94) both; }}

#note-detail {{
  padding: 18px 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}}
#note-detail.hidden {{ display: none; }}
.note-header {{
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border-glass);
}}
#note-title {{
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  line-height: 1.4;
  margin: 0;
}}
#note-meta {{ display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }}

.badge {{
  display: inline-flex;
  align-items: center;
  padding: 2px 9px;
  border-radius: 20px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.6px;
  text-transform: uppercase;
}}
.badge.hidden {{ display: none; }}
.badge.projects  {{ background: rgba(108, 92, 231, 0.18); color: #a78bfa; border: 1px solid rgba(108,92,231,0.35); }}
.badge.areas     {{ background: rgba(0, 184, 148, 0.15);  color: #34d399; border: 1px solid rgba(0,184,148,0.35); }}
.badge.resources {{ background: rgba(9, 132, 227, 0.15);  color: #60a5fa; border: 1px solid rgba(9,132,227,0.35); }}
.badge.archives  {{ background: rgba(99, 110, 114, 0.18); color: #94a3b8; border: 1px solid rgba(99,110,114,0.35); }}

.tags-container {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.tag {{
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  background: var(--bg-glass);
  border: 1px solid var(--border-glass);
}}

.note-body {{ flex: 1; }}
#note-content-preview {{
  font-size: 13px;
  line-height: 1.75;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}}
.word-count-hint {{ display: block; margin-top: 8px; font-size: 11px; color: var(--text-muted); }}

#note-related-container {{ border-top: 1px solid var(--border-glass); padding-top: 12px; }}
#note-related-container.hidden {{ display: none; }}
.related-heading {{ font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }}
#note-related-list {{ list-style: none; display: flex; flex-direction: column; gap: 4px; }}
#note-related-list li a {{
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  background: var(--bg-glass);
  border: 1px solid var(--border-glass);
  transition: all var(--transition);
}}
#note-related-list li a::before {{ content: '→'; font-size: 12px; color: var(--accent-projects); flex-shrink: 0; }}
#note-related-list li a:hover {{
  color: var(--text-primary);
  background: var(--bg-glass-hover);
  border-color: var(--border-glow);
  transform: translateX(3px);
}}

/* Tooltip */
.node-tooltip {{
  position: fixed;
  z-index: 200;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: rgba(18, 18, 42, 0.96);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-glass);
  box-shadow: 0 8px 32px rgba(0,0,0,0.5);
  max-width: 260px;
  pointer-events: none;
  font-size: 12px;
  color: var(--text-secondary);
  animation: fadeIn 150ms ease;
}}
.tooltip-title {{ font-weight: 600; font-size: 13px; color: var(--text-primary); margin-bottom: 4px; }}
@keyframes fadeIn {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}

/* Responsive */
@media (max-width: 680px) {{
  #main-content {{ grid-template-columns: 1fr; grid-template-rows: 60% 1fr; }}
  #graph-section {{ border-right: none; border-bottom: 1px solid var(--border-glass); }}
  .stats-bar {{ display: none; }}
}}
</style>
</head>
<body>
<main id="main-content">
  <!-- Left: Graph -->
  <section id="graph-section">
    <div class="graph-filters">
      <span>Filter:</span>
      <button class="filter-btn active" data-category="projects">Projects</button>
      <button class="filter-btn active" data-category="areas">Areas</button>
      <button class="filter-btn active" data-category="resources">Resources</button>
      <button class="filter-btn active" data-category="archives">Archives</button>
    </div>
    <div id="graph-container">
      <div id="graph-empty-state" class="hidden">
        <div class="empty-state-icon">🌱</div>
        <h2 class="empty-state-heading">Your second brain is empty</h2>
        <p class="empty-state-body">Capture your first note, URL, or document to begin building your personal knowledge graph.</p>
      </div>
    </div>
    <div class="stats-bar">
      <div class="stats-bar-inner">
        <div class="stat-card" id="sc-projects">
          <span class="stat-card-count">0</span>
          <span class="stat-card-label">Projects</span>
          <span class="stat-card-dot" style="background:var(--accent-projects)"></span>
        </div>
        <div class="stat-card" id="sc-areas">
          <span class="stat-card-count">0</span>
          <span class="stat-card-label">Areas</span>
          <span class="stat-card-dot" style="background:var(--accent-areas)"></span>
        </div>
        <div class="stat-card" id="sc-resources">
          <span class="stat-card-count">0</span>
          <span class="stat-card-label">Resources</span>
          <span class="stat-card-dot" style="background:var(--accent-resources)"></span>
        </div>
        <div class="stat-card" id="sc-archives">
          <span class="stat-card-count">0</span>
          <span class="stat-card-label">Archives</span>
          <span class="stat-card-dot" style="background:var(--accent-archives)"></span>
        </div>
        <div class="stat-card stat-card-total" id="sc-total">
          <span class="stat-card-count">0</span>
          <span class="stat-card-label">Total</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Right: Note Panel -->
  <aside id="note-panel">
    <div id="note-panel-content">
      <div id="note-panel-empty" class="note-panel-empty">
        <div class="note-panel-empty-icon">◎</div>
        <p class="note-panel-empty-text">Click a node in the graph<br>to explore its content.</p>
      </div>
      <div id="note-detail" class="hidden">
        <header class="note-header">
          <h2 id="note-title">—</h2>
          <div id="note-meta">
            <span id="note-category" class="badge hidden"></span>
            <div id="note-tags" class="tags-container"></div>
          </div>
        </header>
        <div class="note-body">
          <div id="note-content-preview"></div>
        </div>
        <div id="note-related-container" class="hidden">
          <h3 class="related-heading">Related Notes</h3>
          <ul id="note-related-list"></ul>
        </div>
      </div>
    </div>
  </aside>
</main>

<script>
'use strict';

// ── Injected Data ──────────────────────────────────────────────
const rawNodes = {nodes_json};
const rawEdges = {edges_json};
const graphMeta = {meta_json};

// ── State ──────────────────────────────────────────────────────
let _network = null;
let _nodesMap = {{}};
let _tooltip = null;
let _selectedNode = null;

const EDGE_DEFAULT   = {{ color: 'rgba(148, 163, 184, 0.2)', opacity: 1 }};
const EDGE_HIGHLIGHT = {{ color: 'rgba(108, 92, 231, 0.85)', opacity: 1 }};
const EDGE_DIM       = {{ color: 'rgba(148, 163, 184, 0.06)', opacity: 1 }};

// ── Category Filters ───────────────────────────────────────────
let _activeCategories = new Set(['projects', 'areas', 'resources', 'archives']);

// ── Init ───────────────────────────────────────────────────────
(function init() {{
  const container = document.getElementById('graph-container');
  const emptyState = document.getElementById('graph-empty-state');

  if (rawNodes.length === 0) {{
    emptyState.classList.remove('hidden');
    return;
  }}

  emptyState.classList.add('hidden');

  // Build lookup
  rawNodes.forEach(n => _nodesMap[n.id] = n);

  // Transform nodes
  const visNodes = rawNodes.map((node, i) => {{
    const linkCount = node.link_count || 0;
    const size = Math.min(42, Math.max(14, 14 + linkCount * 6));
    const hue = (i * 137.508) % 360;
    return {{
      id: node.id,
      label: node.label && node.label.length > 22 ? node.label.slice(0, 22) + '…' : (node.label || ''),
      size,
      color: {{
        background: `hsl(${{hue}}, 70%, 55%)`,
        border: `hsl(${{hue}}, 75%, 65%)`,
        highlight: {{ background: `hsl(${{hue}}, 80%, 65%)`, border: `hsl(${{hue}}, 85%, 75%)` }},
      }},
      shape: 'dot',
      font: {{ color: '#e2e8f0', size: 12, face: 'Inter, sans-serif' }},
      shadow: {{ enabled: true, color: 'rgba(0,0,0,0.45)', size: 8, x: 2, y: 2 }},
    }};
  }});

  // Transform edges
  const visEdges = rawEdges.map((e, i) => ({{
    id: 'e-' + i,
    from: e.from,
    to: e.to,
    width: 1.5,
    color: EDGE_DEFAULT,
    smooth: {{ type: 'dynamic' }},
    arrows: {{ to: {{ enabled: false }} }},
  }}));

  const data = {{
    nodes: new vis.DataSet(visNodes),
    edges: new vis.DataSet(visEdges),
  }};

  _network = new vis.Network(container, data, {{
    nodes: {{ shape: 'dot', borderWidth: 2, borderWidthSelected: 3 }},
    edges: {{ smooth: {{ type: 'dynamic' }}, color: {{ inherit: false }}, selectionWidth: 0 }},
    physics: {{
      enabled: true,
      solver: 'barnesHut',
      barnesHut: {{ gravitationalConstant: -3000, centralGravity: 0.3, springLength: 120, springConstant: 0.04, damping: 0.3, avoidOverlap: 0.1 }},
      stabilization: {{ iterations: 250, updateInterval: 25 }},
    }},
    interaction: {{ hover: true, tooltipDelay: 100, dragNodes: true, zoomView: true, keyboard: {{ enabled: true }} }},
    layout: {{ improvedLayout: true }},
  }});

  _network.once('stabilizationIterationsDone', () => {{
    _network.setOptions({{ physics: {{ enabled: false }} }});
    _network.fit({{ animation: {{ duration: 800, easingFunction: 'easeOutQuart' }} }});
  }});

  // ── Interactions ─────────────────────────────────────────────
  _network.on('hoverNode', (p) => {{
    const node = _nodesMap[p.node];
    if (!node) return;
    _removeTooltip();
    _tooltip = document.createElement('div');
    _tooltip.className = 'node-tooltip';
    const tags = Array.isArray(node.tags) && node.tags.length
      ? node.tags.map(t => '<span style="opacity:.7">#' + t + '</span>').join(' ') : '';
    const summary = node.summary ? '<div style="margin-top:5px;opacity:.8;">' + (node.summary.length > 120 ? node.summary.slice(0,120) + '…' : node.summary) + '</div>' : '';
    const badge = node.category ? '<span style="font-size:10px;padding:1px 6px;border-radius:8px;background:rgba(255,255,255,.08);color:#94a3b8">' + node.category + '</span>' : '';
    const links = node.link_count ? '<div style="margin-top:4px;font-size:10px;color:#64748b">' + node.link_count + ' link' + (node.link_count !== 1 ? 's' : '') + '</div>' : '';
    _tooltip.innerHTML = '<div class="tooltip-title">' + (node.label || node.id) + '</div>' + badge + summary + links + (tags ? '<div style="margin-top:5px;font-size:11px">' + tags + '</div>' : '');
    document.body.appendChild(_tooltip);
    _positionTooltip(p.event);
  }});
  _network.on('blurNode', () => _removeTooltip());
  _network.on('mouseMoved', (p) => {{ if (_tooltip) _positionTooltip(p.event); }});

  _network.on('click', (p) => {{
    _removeTooltip();
    if (p.nodes.length > 0) {{
      _selectedNode = p.nodes[0];
      showNoteDetail(_selectedNode);
      _highlightEdges(_selectedNode, data.edges);
      _network.selectNodes([_selectedNode], false);
    }} else {{
      _selectedNode = null;
      resetNotePanel();
      _resetEdges(data.edges);
      _network.unselectAll();
    }}
  }});

  _network.on('doubleClick', (p) => {{
    if (p.nodes.length > 0) {{
      _network.focus(p.nodes[0], {{ scale: 1.5, animation: {{ duration: 600, easingFunction: 'easeInOutQuad' }} }});
    }}
  }});

  _network.on('dragStart', () => _removeTooltip());

  // ── Category Filters ─────────────────────────────────────────
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const cat = btn.dataset.category;
      if (_activeCategories.has(cat)) {{
        _activeCategories.delete(cat);
        btn.classList.remove('active');
      }} else {{
        _activeCategories.add(cat);
        btn.classList.add('active');
      }}
      const updates = data.nodes.getIds().map(id => {{
        const n = _nodesMap[id];
        const c = (n && n.category) ? n.category : 'resources';
        return {{ id, hidden: !_activeCategories.has(c) }};
      }});
      data.nodes.update(updates);
    }});
  }});

  // ── Stats Dashboard ──────────────────────────────────────────
  const by = graphMeta.category_counts || {{}};
  ['projects', 'areas', 'resources', 'archives'].forEach(cat => {{
    const el = document.querySelector('#sc-' + cat + ' .stat-card-count');
    if (el) el.textContent = by[cat] || 0;
  }});
  const totalEl = document.querySelector('#sc-total .stat-card-count');
  if (totalEl) totalEl.textContent = graphMeta.total_nodes || 0;

  // ── Graph meta badge ─────────────────────────────────────────
  const badge = document.createElement('div');
  badge.className = 'graph-meta-badge';
  badge.innerHTML =
    '<span class="graph-meta-pill" style="--pill-color:#a78bfa">Nodes <strong>' + (graphMeta.total_nodes || 0) + '</strong></span>' +
    '<span class="graph-meta-pill" style="--pill-color:#60a5fa">Edges <strong>' + (graphMeta.total_edges || 0) + '</strong></span>';
  container.appendChild(badge);
}})();

// ── Note Panel ─────────────────────────────────────────────────
function showNoteDetail(nodeId) {{
  const node = _nodesMap[nodeId];
  if (!node) return;
  const emptyEl = document.getElementById('note-panel-empty');
  const detailEl = document.getElementById('note-detail');
  if (emptyEl) emptyEl.style.display = 'none';
  if (detailEl) {{
    detailEl.classList.remove('hidden');
    detailEl.classList.add('panel-enter');
    requestAnimationFrame(() => detailEl.classList.remove('panel-enter'));
  }}

  document.getElementById('note-title').textContent = node.label || 'Untitled';
  const badge = document.getElementById('note-category');
  badge.textContent = node.category || '';
  badge.className = 'badge ' + (node.category || '');
  badge.classList.remove('hidden');

  const tagsC = document.getElementById('note-tags');
  tagsC.innerHTML = '';
  (Array.isArray(node.tags) ? node.tags : []).forEach(t => {{
    const chip = document.createElement('span');
    chip.className = 'tag';
    chip.textContent = '#' + t;
    tagsC.appendChild(chip);
  }});

  const preview = document.getElementById('note-content-preview');
  preview.innerHTML = '';
  const text = node.content_preview || node.summary || '';
  const textEl = document.createElement('div');
  textEl.style.whiteSpace = 'pre-wrap';
  textEl.textContent = text;
  preview.appendChild(textEl);
  if (node.word_count) {{
    const wc = document.createElement('small');
    wc.className = 'word-count-hint';
    wc.textContent = node.word_count + ' words';
    preview.appendChild(wc);
  }}

  const relContainer = document.getElementById('note-related-container');
  const relList = document.getElementById('note-related-list');
  relList.innerHTML = '';
  const relatedIds = _network ? [...new Set(_network.getConnectedNodes(nodeId))].filter(id => id !== nodeId) : [];
  if (relatedIds.length > 0) {{
    relatedIds.forEach(relId => {{
      const rel = _nodesMap[relId];
      if (!rel) return;
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = '#';
      a.textContent = rel.label || relId;
      a.addEventListener('click', (e) => {{
        e.preventDefault();
        showNoteDetail(relId);
        if (_network) {{
          _network.selectNodes([relId], false);
          _highlightEdges(relId, _network.body.data.edges);
        }}
      }});
      li.appendChild(a);
      relList.appendChild(li);
    }});
    relContainer.classList.remove('hidden');
  }} else {{
    relContainer.classList.add('hidden');
  }}

  document.getElementById('note-panel-content').scrollTop = 0;
}}

function resetNotePanel() {{
  const emptyEl = document.getElementById('note-panel-empty');
  const detailEl = document.getElementById('note-detail');
  if (detailEl) detailEl.classList.add('hidden');
  if (emptyEl) emptyEl.style.display = '';
}}

// ── Helpers ────────────────────────────────────────────────────
function _highlightEdges(nodeId, edgesDS) {{
  const connected = new Set(_network.getConnectedEdges(nodeId));
  edgesDS.update(edgesDS.getIds().map(eid => ({{
    id: eid,
    color: connected.has(eid) ? EDGE_HIGHLIGHT : EDGE_DIM,
    width: connected.has(eid) ? 2.5 : 1,
  }})));
}}
function _resetEdges(edgesDS) {{
  edgesDS.update(edgesDS.getIds().map(eid => ({{ id: eid, color: EDGE_DEFAULT, width: 1.5 }})));
}}
function _removeTooltip() {{ if (_tooltip) {{ _tooltip.remove(); _tooltip = null; }} }}
function _positionTooltip(event) {{
  if (!_tooltip) return;
  const pad = 16;
  const rect = _tooltip.getBoundingClientRect();
  let x = (event.clientX || 0) + pad;
  let y = (event.clientY || 0) + pad;
  if (x + rect.width > window.innerWidth) x -= rect.width + pad * 2;
  if (y + rect.height > window.innerHeight) y -= rect.height + pad * 2;
  _tooltip.style.left = x + 'px';
  _tooltip.style.top = y + 'px';
}}
</script>
</body>
</html>
"""

# ═══════════════════════════════════════════════════════════════════════════════
#  RENDER PAGE
# ═══════════════════════════════════════════════════════════════════════════════

# ── Data ──────────────────────────────────────────────────────────────────────
wiki_count = sum(1 for _ in WIKI_DIR.rglob("*.md")) if WIKI_DIR.exists() else 0
try: embedded_count = get_engine().collection.count()
except: embedded_count = 0
graph_data = _get_graph_data()

# ── Header ────────────────────────────────────────────────────────────────────
header_html = f'''
<div class="app-header">
    <div class="logo">
        <span class="logo-icon">🧠</span>
        <span class="logo-text">ASHISH'S BRaIN</span>
    </div>
    <div class="header-nav">
        <div class="stats-pill">
            <span class="stats-icon">◈</span> {wiki_count} notes
            <span class="stats-divider">·</span>
            <span class="stats-icon">⚡</span> {embedded_count} embedded
        </div>
    </div>
</div>
'''
st.markdown(header_html, unsafe_allow_html=True)

# ── Capture Button ────────────────────────────────────────────────────────────
col_spacer, col_btn = st.columns([8.5, 1.5])
with col_btn:
    if st.button("✦ Capture", use_container_width=True, type="primary"):
        capture_modal()

# ── Graph Component ───────────────────────────────────────────────────────────
graph_html = _build_graph_html(graph_data, wiki_count, embedded_count)
components.html(graph_html, height=620, scrolling=False)

# ═══════════════════════════════════════════════════════════════════════════════
#  ASK BAR & ANSWER DISPLAY
# ═══════════════════════════════════════════════════════════════════════════════

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

# ── Show last answer ──────────────────────────────────────────────────────────
if st.session_state.chat_history:
    last_msg = st.session_state.chat_history[-1]
    if last_msg["role"] == "assistant" and len(st.session_state.chat_history) >= 2:
        user_q = st.session_state.chat_history[-2]["content"]
        confidence = last_msg.get("confidence", "low")
        conf_color = {"high": "#34d399", "medium": "#fbbf24", "low": "#f87171"}.get(confidence, "#94a3b8")
        conf_label = {"high": "● High", "medium": "◐ Medium", "low": "○ Low"}.get(confidence, confidence)

        # Source chips
        sources_html = ""
        if last_msg.get("sources"):
            chips = "".join(
                f'<span class="source-chip" title="Similarity: {int(s["similarity"]*100)}%">{s["title"]}</span>'
                for s in last_msg["sources"]
            )
            sources_html = f'<div class="answer-sources"><span class="sources-label">Sources:</span>{chips}</div>'

        timing_html = ""
        if last_msg.get("timings"):
            t = last_msg["timings"]
            timing_html = f'<span class="timing-info">⏱ {t.get("retrieve", 0)}ms retrieve · {t.get("llm", 0)}ms LLM</span>'

        answer_html = f'''
        <div class="answer-card">
            <div class="answer-header">
                <span class="answer-question">"{user_q}"</span>
                <div class="answer-meta">
                    <span class="conf-badge" style="color:{conf_color}">{conf_label} confidence</span>
                    {timing_html}
                </div>
            </div>
            <div class="answer-body">{last_msg["content"]}</div>
            {sources_html}
        </div>
        '''
        st.markdown(answer_html, unsafe_allow_html=True)

# ── Ask Input ─────────────────────────────────────────────────────────────────
question = st.chat_input("Ask your second brain anything… ")
if question:
    st.session_state.chat_history.append({"role": "user", "content": question})

    with st.spinner("Searching your knowledge base…"):
        try:
            from secondself.ask import ask
            engine = get_engine()
            res = ask(question, engine)

            sources_data = [{"id": s.id, "title": s.title, "similarity": s.similarity} for s in res.sources]
            st.session_state.chat_history.append({
                "role": "assistant",
                "content": res.answer,
                "sources": sources_data,
                "confidence": res.confidence,
                "timings": {
                    "retrieve": round(res.query_embedding_time_ms + res.retrieval_time_ms),
                    "llm": round(res.llm_time_ms),
                },
            })
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
