"""
SecondSelf — Streamlit App

Replaces the FastAPI server + vanilla-JS frontend with a single Streamlit
application.  All core modules (capture, classify, embed, link, ask,
graph_builder) are called directly — zero changes to the backend logic.

Run locally:
    uv run streamlit run streamlit_app.py

Deploy:
    Push to GitHub → connect at share.streamlit.io
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

# ── Ensure Streamlit secrets are available as env vars ────────────────────────
# On Streamlit Cloud, secrets come from the dashboard, not .env.
# Locally, the .env file is loaded by classify.py / ask.py via python-dotenv.
try:
    if "GROQ_API_KEY" in st.secrets:
        os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
except FileNotFoundError:
    pass  # No secrets.toml — rely on .env / system env vars

# ── Import SecondSelf modules (unchanged) ────────────────────────────────────
from secondself.config import (
    WIKI_DIR, RAW_DIR, DATA_DIR, GRAPH_JSON,
    PARA_CATEGORIES, CHROMA_DIR,
)
from secondself.graph_builder import build_graph, export_graph
from secondself.embed import EmbeddingEngine
from secondself.capture import capture_note, capture_url, list_captures
from secondself.classify import classify_capture
from secondself.linker import find_related, update_backlinks
from secondself.wiki_writer import write_wiki_note


# ═══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

CATEGORY_COLORS = {
    "projects":  "#6C5CE7",
    "areas":     "#00B894",
    "resources": "#0984E3",
    "archives":  "#636E72",
}

CATEGORY_EMOJI = {
    "projects":  "🟣",
    "areas":     "🟢",
    "resources": "🔵",
    "archives":  "⚪",
}


# ═══════════════════════════════════════════════════════════════════════════════
#  CACHED RESOURCES
# ═══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner="Loading AI models…")
def get_engine() -> EmbeddingEngine:
    """Singleton EmbeddingEngine — loaded once per app session.

    On Streamlit Cloud the ChromaDB directory is ephemeral (not committed to
    git), so we auto-populate it from the wiki notes that *are* in the repo.
    """
    engine = EmbeddingEngine()
    _auto_populate_chroma(engine)
    return engine


def _auto_populate_chroma(engine: EmbeddingEngine) -> None:
    """Re-embed all wiki notes into ChromaDB if the collection is empty.

    This makes the deployed app functional on first launch without requiring
    the user to manually run ``secondself process``.
    """
    if engine.collection.count() > 0:
        return  # Already populated

    if not WIKI_DIR.exists():
        return

    md_files = list(WIKI_DIR.rglob("*.md"))
    if not md_files:
        return

    for md_file in md_files:
        try:
            raw = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        # Parse frontmatter
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not fm_match:
            continue

        fm_data: dict[str, str] = {}
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                fm_data[key.strip()] = val.strip().strip('"').strip("'")

        note_id = fm_data.get("id", md_file.stem)
        title = fm_data.get("title", md_file.stem)
        category = fm_data.get("category", "resources")
        tags_str = fm_data.get("tags", "[]")
        created = fm_data.get("created", "")

        # Extract body text (after frontmatter)
        body = raw[fm_match.end():]
        # Remove markdown headings and blockquotes for cleaner embedding
        text_lines = [
            ln for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith(("#", ">"))
        ]
        text = "\n".join(text_lines).strip()
        if not text:
            text = title  # Fallback

        try:
            engine.store(
                capture_id=note_id,
                text=text,
                metadata={
                    "title": title,
                    "category": category,
                    "tags": tags_str,
                    "timestamp": created,
                },
            )
        except Exception:
            continue  # Skip notes that fail to embed


def _get_graph_data() -> dict:
    """Return graph dict, rebuilding if wiki/ is newer than cache."""
    if not WIKI_DIR.exists():
        return {"nodes": [], "edges": [], "metadata": {}}

    md_files = list(WIKI_DIR.rglob("*.md"))
    if not md_files:
        return {"nodes": [], "edges": [], "metadata": {}}

    newest_wiki = max(f.stat().st_mtime for f in md_files)

    if GRAPH_JSON.exists() and GRAPH_JSON.stat().st_mtime >= newest_wiki:
        try:
            with open(GRAPH_JSON, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Rebuild
    graph_data = build_graph(WIKI_DIR)
    try:
        export_graph(WIKI_DIR, GRAPH_JSON)
    except Exception:
        pass
    return graph_data


def _parse_note_meta(md_file: Path) -> dict:
    """Parse frontmatter of a wiki note into a summary dict."""
    try:
        raw = md_file.read_text(encoding="utf-8")
    except OSError:
        return {"id": md_file.stem, "title": md_file.stem}

    meta: dict = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                meta[key.strip()] = val.strip().strip('"').strip("'")

    # Tags
    tags_str = meta.get("tags", "[]")
    try:
        tags = json.loads(tags_str) if tags_str.startswith("[") else []
    except (json.JSONDecodeError, ValueError):
        tags = []
    meta["tags"] = tags

    # Body
    body_start = fm_match.end() if fm_match else 0
    body = raw[body_start:]
    meta["word_count"] = len(body.split())
    meta["body"] = body

    meta.setdefault("id", md_file.stem)
    meta.setdefault("title", md_file.stem)
    meta.setdefault("category", "resources")
    meta.setdefault("created", "")

    try:
        meta["path"] = str(md_file.relative_to(WIKI_DIR))
    except ValueError:
        meta["path"] = md_file.name

    return meta


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="SecondSelf — Your AI Second Brain",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS injection for premium look ────────────────────────────────────
st.markdown("""
<style>
    /* Import Inter font */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global */
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0d0d24 0%, #12122a 100%);
        border-right: 1px solid rgba(255,255,255,0.06);
    }

    /* Main header */
    .main-title {
        font-size: 2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #6C5CE7 0%, #0984E3 50%, #00B894 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
        letter-spacing: -0.02em;
    }

    .subtitle {
        color: #94a3b8;
        font-size: 0.95rem;
        margin-top: -0.5rem;
    }

    /* Badge styling */
    .category-badge {
        display: inline-block;
        padding: 0.2rem 0.65rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
        text-transform: uppercase;
    }
    .badge-projects  { background: rgba(108,92,231,0.2);  color: #9b89ff; border: 1px solid rgba(108,92,231,0.3); }
    .badge-areas     { background: rgba(0,184,148,0.2);   color: #00d4aa; border: 1px solid rgba(0,184,148,0.3); }
    .badge-resources { background: rgba(9,132,227,0.2);   color: #2fa8ff; border: 1px solid rgba(9,132,227,0.3); }
    .badge-archives  { background: rgba(99,110,114,0.2);  color: #8a979b; border: 1px solid rgba(99,110,114,0.3); }

    /* Tag chips */
    .tag-chip {
        display: inline-block;
        padding: 0.15rem 0.5rem;
        border-radius: 12px;
        font-size: 0.7rem;
        font-weight: 500;
        background: rgba(255,255,255,0.06);
        color: #94a3b8;
        border: 1px solid rgba(255,255,255,0.08);
        margin: 0.15rem;
    }

    /* Metric cards */
    [data-testid="stMetric"] {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 12px;
        padding: 1rem;
    }

    /* Glass card effect */
    .glass-card {
        background: rgba(255,255,255,0.04);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 16px;
        padding: 1.5rem;
        margin-bottom: 1rem;
    }

    /* Source card */
    .source-card {
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 0.8rem 1rem;
        margin: 0.4rem 0;
    }

    /* Confidence badges */
    .confidence-high   { color: #00B894; font-weight: 600; }
    .confidence-medium { color: #fdcb6e; font-weight: 600; }
    .confidence-low    { color: #e17055; font-weight: 600; }

    /* Pulse animation for recent items */
    @keyframes subtle-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.7; }
    }
    .recent-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #00B894;
        animation: subtle-pulse 2s ease-in-out infinite;
        margin-right: 6px;
    }

    /* Smooth divider */
    .divider {
        height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
        margin: 1.5rem 0;
    }

    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown('<p class="main-title">🧠 ASHISH BRAIN</p>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">APNA SAATHI </p>', unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    page = st.radio(
        "Navigate",
        ["🧠 Knowledge Graph", "💬 Ask Your Brain", "📥 Capture", "📊 Dashboard"],
        index=0,
        label_visibility="collapsed",
    )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # Quick stats in sidebar
    wiki_count = sum(1 for _ in WIKI_DIR.rglob("*.md")) if WIKI_DIR.exists() else 0
    raw_count = len(list(RAW_DIR.glob("*.json"))) if RAW_DIR.exists() else 0

    col1, col2 = st.columns(2)
    col1.metric("📝 Notes", wiki_count)
    col2.metric("📦 Captures", raw_count)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    st.caption("Built with ❤️ by Ashish Kumar Verma")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: KNOWLEDGE GRAPH
# ═══════════════════════════════════════════════════════════════════════════════

if page == "🧠 GYAN KA DUKAN":
    st.markdown("## 🧠 GYAN KA DUKAN")
    st.markdown(
        '<p class="subtitle">Explore your interconnected knowledge — '
        "click any node to see its content.</p>",
        unsafe_allow_html=True,
    )

    graph_data = _get_graph_data()
    nodes_data = graph_data.get("nodes", [])
    edges_data = graph_data.get("edges", [])

    if not nodes_data:
        st.info(
            "🌱 **Your second brain is empty.**\n\n"
            "Head to the **📥 Capture** page to add your first note, "
            "or run `uv run secondself process` in your terminal to import "
            "notes from `raw/`."
        )
    else:
        # Build node lookup
        node_lookup = {n["id"]: n for n in nodes_data}

        # Create agraph nodes
        ag_nodes = []
        for n in nodes_data:
            cat = n.get("category", "resources")
            size = max(15, min(45, 15 + n.get("link_count", 0) * 6))
            ag_nodes.append(
                Node(
                    id=n["id"],
                    label=n.get("label", n["id"][:12]),
                    size=size,
                    color=CATEGORY_COLORS.get(cat, "#0984E3"),
                    title=f"{n.get('label', '')}\n\n{n.get('summary', '')}",
                    font={"color": "#e2e8f0", "size": 11},
                )
            )

        # Create agraph edges
        ag_edges = []
        for e in edges_data:
            ag_edges.append(
                Edge(
                    source=e["from"],
                    target=e["to"],
                    color="rgba(148, 163, 184, 0.25)",
                    width=1.5,
                )
            )

        # Graph config
        config = Config(
            width="100%",
            height=550,
            directed=False,
            physics={
                "enabled": True,
                "barnesHut": {
                    "gravitationalConstant": -3000,
                    "centralGravity": 0.3,
                    "springLength": 120,
                    "springConstant": 0.04,
                    "damping": 0.3,
                },
            },
            hierarchical=False,
            nodeHighlightBehavior=True,
            highlightColor="#6C5CE7",
            collapsible=False,
        )

        # Render graph and capture selection
        selected_node_id = agraph(
            nodes=ag_nodes,
            edges=ag_edges,
            config=config,
        )

        # Legend
        legend_cols = st.columns(4)
        for i, (cat, color) in enumerate(CATEGORY_COLORS.items()):
            legend_cols[i].markdown(
                f'<span style="color:{color}; font-size:1.3rem;">●</span> '
                f'<span style="color:#94a3b8; font-size:0.85rem;">{cat.title()}</span>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

        # ── Note detail panel ─────────────────────────────────────────────
        if selected_node_id and selected_node_id in node_lookup:
            node = node_lookup[selected_node_id]
            cat = node.get("category", "resources")
            badge_cls = f"badge-{cat}"

            st.markdown(f"### {node.get('label', 'Untitled')}")
            st.markdown(
                f'<span class="category-badge {badge_cls}">'
                f'{CATEGORY_EMOJI.get(cat, "📄")} {cat}</span>',
                unsafe_allow_html=True,
            )

            tags = node.get("tags", [])
            if tags:
                tags_html = " ".join(
                    f'<span class="tag-chip">{t.strip()}</span>' for t in tags if t.strip()
                )
                st.markdown(tags_html, unsafe_allow_html=True)

            if node.get("summary"):
                st.markdown(f"> {node['summary']}")

            if node.get("content_preview"):
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.markdown(node["content_preview"])
                st.markdown("</div>", unsafe_allow_html=True)

            # Show full note content from wiki file
            wiki_file = _find_wiki_file(selected_node_id)
            if wiki_file:
                with st.expander("📖 Full Note Content", expanded=False):
                    meta = _parse_note_meta(wiki_file)
                    st.markdown(meta.get("body", "*(No content)*"))

            st.caption(
                f"Created: {node.get('created', 'N/A')} · "
                f"Words: {node.get('word_count', 0)} · "
                f"Links: {node.get('link_count', 0)}"
            )
        else:
            st.markdown(
                '<div class="glass-card" style="text-align:center; padding:2rem;">'
                '<p style="font-size:2rem; margin-bottom:0.5rem;">◎</p>'
                '<p style="color:#94a3b8;">Click a node in the graph to explore its content.</p>'
                "</div>",
                unsafe_allow_html=True,
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: ASK YOUR BRAIN
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "💬 Ask Your Brain":
    st.markdown("## 💬 Ask Your Brain")
    st.markdown(
        '<p class="subtitle">'
        "Ask a natural-language question — AI answers using your notes with citations."
        "</p>",
        unsafe_allow_html=True,
    )

    # Init chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"], avatar="🧑‍💻" if msg["role"] == "user" else "🧠"):
            st.markdown(msg["content"])
            if msg.get("sources"):
                with st.expander(f"📚 Sources ({len(msg['sources'])})"):
                    for src in msg["sources"]:
                        sim_pct = round(src["similarity"] * 100)
                        st.markdown(
                            f'<div class="source-card">'
                            f'<strong>{src["title"]}</strong> '
                            f'<span style="color:#6C5CE7;">({sim_pct}% match)</span><br>'
                            f'<span style="color:#94a3b8; font-size:0.85rem;">'
                            f'{src["excerpt"][:150]}…</span></div>',
                            unsafe_allow_html=True,
                        )
            if msg.get("confidence"):
                conf = msg["confidence"]
                cls = f"confidence-{conf}"
                st.markdown(
                    f'<span class="{cls}">Confidence: {conf.upper()}</span>',
                    unsafe_allow_html=True,
                )

    # Chat input
    question = st.chat_input("Ask your second brain anything…")

    if question:
        # Show user message
        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(question)

        # Generate answer
        with st.chat_message("assistant", avatar="🧠"):
            with st.spinner("Searching your knowledge base…"):
                try:
                    from secondself.ask import ask
                    engine = get_engine()
                    response = ask(question, engine)

                    st.markdown(response.answer)

                    sources_data = []
                    if response.sources:
                        with st.expander(f"📚 Sources ({len(response.sources)})"):
                            for src in response.sources:
                                sim_pct = round(src.similarity * 100)
                                st.markdown(
                                    f'<div class="source-card">'
                                    f'<strong>{src.title}</strong> '
                                    f'<span style="color:#6C5CE7;">({sim_pct}% match)</span><br>'
                                    f'<span style="color:#94a3b8; font-size:0.85rem;">'
                                    f'{src.excerpt[:150]}…</span></div>',
                                    unsafe_allow_html=True,
                                )
                                sources_data.append({
                                    "title": src.title,
                                    "similarity": src.similarity,
                                    "excerpt": src.excerpt,
                                })

                    conf = response.confidence
                    cls = f"confidence-{conf}"
                    st.markdown(
                        f'<span class="{cls}">Confidence: {conf.upper()}</span> · '
                        f'<span style="color:#636E72; font-size:0.8rem;">'
                        f"Embed: {response.query_embedding_time_ms:.0f}ms · "
                        f"Retrieve: {response.retrieval_time_ms:.0f}ms · "
                        f"LLM: {response.llm_time_ms:.0f}ms</span>",
                        unsafe_allow_html=True,
                    )

                    # Save to history
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": response.answer,
                        "sources": sources_data,
                        "confidence": conf,
                    })

                except Exception as e:
                    error_msg = f"❌ Error: {e}"
                    st.error(error_msg)
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": error_msg,
                    })


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: CAPTURE
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📥 Capture":
    st.markdown("## 📥 Capture New Knowledge")
    st.markdown(
        '<p class="subtitle">'
        "Capture a note or URL — it will be automatically classified, embedded, and linked."
        "</p>",
        unsafe_allow_html=True,
    )

    tab_note, tab_url = st.tabs(["📝 Note", "🔗 URL"])

    with tab_note:
        st.markdown("#### Capture a Text Note")
        note_text = st.text_area(
            "Your note",
            height=160,
            placeholder="Type or paste your note here…\n\nExample: The Feynman Technique helps you learn by explaining concepts in simple terms.",
            label_visibility="collapsed",
        )
        btn_note = st.button("✦ Capture Note", type="primary", use_container_width=True)

        if btn_note and note_text.strip():
            with st.spinner("Capturing → Classifying → Embedding → Linking…"):
                try:
                    # 1. Capture
                    capture = capture_note(note_text.strip())

                    # 2. Classify
                    classification = classify_capture(capture)

                    # 3. Embed
                    engine = get_engine()
                    content_text = capture.get("content", {}).get("text", "")
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

                    # 4. Find related
                    try:
                        related = find_related(capture["id"], engine)
                    except Exception:
                        related = []

                    # 5. Write wiki note
                    wiki_path = write_wiki_note(capture, classification, related)

                    # 6. Backlinks
                    if related:
                        update_backlinks(WIKI_DIR, classification.suggested_title, related)

                    # Invalidate graph cache
                    if GRAPH_JSON.exists():
                        GRAPH_JSON.unlink()

                    # Success
                    cat = classification.category
                    badge_cls = f"badge-{cat}"

                    st.success(f"✅ Captured and processed successfully!")
                    st.markdown(
                        f'<div class="glass-card">'
                        f"<strong>{classification.suggested_title}</strong><br>"
                        f'<span class="category-badge {badge_cls}">'
                        f"{CATEGORY_EMOJI.get(cat, '📄')} {cat}</span> "
                        f"&nbsp; Confidence: {classification.confidence:.0%}<br>"
                        f"<em>{classification.summary}</em><br><br>"
                        f"Tags: {', '.join(classification.tags)}<br>"
                        f"Wiki: <code>{wiki_path.relative_to(WIKI_DIR)}</code>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                    if related:
                        st.markdown(f"**🔗 Linked to {len(related)} related note(s):**")
                        for r in related:
                            st.markdown(
                                f"- {r.get('title', r.get('id', '')[:8])} "
                                f"({r.get('similarity', 0):.0%} similar)"
                            )

                except Exception as e:
                    st.error(f"❌ Error: {e}")
        elif btn_note:
            st.warning("Please enter some text before capturing.")

    with tab_url:
        st.markdown("#### Capture a URL")
        url_input = st.text_input(
            "URL",
            placeholder="https://arxiv.org/abs/1706.03762",
            label_visibility="collapsed",
        )
        btn_url = st.button("✦ Capture URL", type="primary", use_container_width=True)

        if btn_url and url_input.strip():
            with st.spinner("Fetching → Classifying → Embedding → Linking…"):
                try:
                    capture = capture_url(url_input.strip())
                    classification = classify_capture(capture)

                    engine = get_engine()
                    content = capture.get("content", {})
                    content_text = f"{content.get('url', '')}\n\n{content.get('text', '')}"
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

                    try:
                        related = find_related(capture["id"], engine)
                    except Exception:
                        related = []

                    wiki_path = write_wiki_note(capture, classification, related)
                    if related:
                        update_backlinks(WIKI_DIR, classification.suggested_title, related)

                    if GRAPH_JSON.exists():
                        GRAPH_JSON.unlink()

                    cat = classification.category
                    badge_cls = f"badge-{cat}"
                    st.success("✅ URL captured and processed!")
                    st.markdown(
                        f'<div class="glass-card">'
                        f"<strong>{classification.suggested_title}</strong><br>"
                        f'<span class="category-badge {badge_cls}">'
                        f"{CATEGORY_EMOJI.get(cat, '📄')} {cat}</span> "
                        f"&nbsp; Confidence: {classification.confidence:.0%}<br>"
                        f"<em>{classification.summary}</em>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

                except Exception as e:
                    st.error(f"❌ Error: {e}")
        elif btn_url:
            st.warning("Please enter a URL before capturing.")


# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE: DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📊 Dashboard":
    st.markdown("## 📊 Dashboard")
    st.markdown(
        '<p class="subtitle">Overview of your personal knowledge base.</p>',
        unsafe_allow_html=True,
    )

    # ── Top metrics ───────────────────────────────────────────────────────
    wiki_count = sum(1 for _ in WIKI_DIR.rglob("*.md")) if WIKI_DIR.exists() else 0
    raw_count = len(list(RAW_DIR.glob("*.json"))) if RAW_DIR.exists() else 0
    try:
        embedded_count = get_engine().collection.count()
    except Exception:
        embedded_count = 0

    col1, col2, col3 = st.columns(3)
    col1.metric("📝 Wiki Notes", wiki_count)
    col2.metric("📦 Raw Captures", raw_count)
    col3.metric("⚡ Embedded", embedded_count)

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── Per-category breakdown ────────────────────────────────────────────
    st.markdown("### Notes by Category")

    cat_cols = st.columns(4)
    for i, cat in enumerate(PARA_CATEGORIES):
        cat_dir = WIKI_DIR / cat
        count = len(list(cat_dir.glob("*.md"))) if cat_dir.exists() else 0
        color = CATEGORY_COLORS.get(cat, "#0984E3")
        emoji = CATEGORY_EMOJI.get(cat, "📄")
        cat_cols[i].markdown(
            f'<div class="glass-card" style="text-align:center;">'
            f'<span style="font-size:2rem;">{emoji}</span><br>'
            f'<span style="font-size:1.8rem; font-weight:700; color:{color};">{count}</span><br>'
            f'<span style="color:#94a3b8; font-size:0.85rem; text-transform:uppercase; '
            f'letter-spacing:0.05em;">{cat}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── Recent captures ──────────────────────────────────────────────────
    st.markdown("### Recent Captures")

    if RAW_DIR.exists():
        raw_files = sorted(RAW_DIR.glob("*.json"), reverse=True)
        if raw_files:
            for rf in raw_files[:8]:
                try:
                    data = json.loads(rf.read_text(encoding="utf-8"))
                    cap_type = data.get("type", "note")
                    title = data.get("metadata", {}).get("title", data.get("id", "")[:8])
                    timestamp = data.get("timestamp", "N/A")
                    type_emoji = {"note": "📝", "url": "🔗", "file": "📄"}.get(cap_type, "📦")

                    st.markdown(
                        f'<div class="source-card">'
                        f'<span class="recent-dot"></span>'
                        f"{type_emoji} <strong>{title}</strong> "
                        f'<span style="color:#636E72; font-size:0.8rem;">· {cap_type} · {timestamp[:19]}</span>'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                except Exception:
                    continue
        else:
            st.info("No captures yet. Head to **📥 Capture** to get started!")
    else:
        st.info("No captures yet.")

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

    # ── All wiki notes list ──────────────────────────────────────────────
    st.markdown("### All Wiki Notes")

    if WIKI_DIR.exists():
        all_notes = []
        for md_file in WIKI_DIR.rglob("*.md"):
            meta = _parse_note_meta(md_file)
            all_notes.append(meta)

        all_notes.sort(key=lambda n: n.get("created", ""), reverse=True)

        if all_notes:
            for note in all_notes:
                cat = note.get("category", "resources")
                badge_cls = f"badge-{cat}"
                emoji = CATEGORY_EMOJI.get(cat, "📄")
                tags = note.get("tags", [])
                tags_html = " ".join(
                    f'<span class="tag-chip">{t.strip()}</span>'
                    for t in tags if t and t.strip()
                )

                with st.expander(f"{emoji} {note.get('title', 'Untitled')}"):
                    st.markdown(
                        f'<span class="category-badge {badge_cls}">{cat}</span>'
                        f" &nbsp; {tags_html}",
                        unsafe_allow_html=True,
                    )
                    st.caption(
                        f"ID: {note.get('id', 'N/A')[:8]} · "
                        f"Words: {note.get('word_count', 0)} · "
                        f"Created: {note.get('created', 'N/A')[:19]}"
                    )
                    body = note.get("body", "")
                    if body:
                        st.markdown(body[:500] + ("…" if len(body) > 500 else ""))
        else:
            st.info("No wiki notes yet.")
    else:
        st.info("Wiki directory not found.")


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPER: Find wiki file by note ID
# ═══════════════════════════════════════════════════════════════════════════════

def _find_wiki_file(note_id: str) -> Path | None:
    """Find a wiki .md file that contains the given note ID in its frontmatter."""
    if not WIKI_DIR.exists():
        return None
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
                if file_id.startswith(note_id) or note_id.startswith(file_id):
                    return md_file
    return None
