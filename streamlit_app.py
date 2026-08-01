"""
SecondSelf — Streamlit App (Single Page Redesign)
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

CATEGORY_EMOJI = {
    "projects":  "🟣",
    "areas":     "🟢",
    "resources": "🔵",
    "archives":  "⚪",
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
                capture_id=note_id,
                text=text,
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

def _parse_note_meta(md_file: Path) -> dict:
    try: raw = md_file.read_text(encoding="utf-8")
    except OSError: return {"id": md_file.stem, "title": md_file.stem}
    meta = {}
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
    if fm_match:
        for line in fm_match.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
    
    tags_str = meta.get("tags", "[]")
    try: meta["tags"] = json.loads(tags_str) if tags_str.startswith("[") else []
    except: meta["tags"] = []
    
    meta["body"] = raw[fm_match.end():] if fm_match else raw
    meta["word_count"] = len(meta["body"].split())
    meta.setdefault("id", md_file.stem)
    meta.setdefault("title", md_file.stem)
    meta.setdefault("category", "resources")
    meta.setdefault("created", "")
    return meta

def _find_wiki_file(note_id: str) -> Path | None:
    if not WIKI_DIR.exists(): return None
    for md_file in WIKI_DIR.rglob("*.md"):
        try: raw = md_file.read_text(encoding="utf-8")
        except: continue
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        if not fm_match: continue
        for line in fm_match.group(1).splitlines():
            if line.strip().startswith("id:"):
                fid = line.split(":", 1)[1].strip().strip('"').strip("'")
                if fid == note_id or note_id.startswith(fid): return md_file
    return None

# ═══════════════════════════════════════════════════════════════════════════════
#  PAGE CONFIG & STYLES
# ═══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="ASHISH'S BRaIN",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    /* Dark glass background */
    .stApp {
        background-color: #0a0a1a;
        background-image: radial-gradient(circle at 1px 1px, rgba(255,255,255,0.04) 1px, transparent 0);
        background-size: 28px 28px;
        color: #e2e8f0;
    }
    
    /* Hide top header and default UI */
    header[data-testid="stHeader"] { display: none; }
    [data-testid="stSidebar"] { display: none; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* App Header Custom UI */
    .app-header-container {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 10px 20px;
        background: rgba(10, 10, 26, 0.8);
        backdrop-filter: blur(20px);
        border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        margin-top: -60px; /* Offset the hidden header */
        margin-left: -3rem;
        margin-right: -3rem;
        margin-bottom: 20px;
    }
    
    .logo-container {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 18px;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    
    .stats-pill {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 5px 14px;
        border-radius: 20px;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        font-size: 12px;
        color: #94a3b8;
    }
    
    /* Badges */
    .category-badge {
        display: inline-block;
        padding: 2px 9px;
        border-radius: 20px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }
    .badge-projects  { background: rgba(108, 92, 231, 0.18); color: #a78bfa; border: 1px solid rgba(108,92,231,0.35); }
    .badge-areas     { background: rgba(0, 184, 148, 0.15);  color: #34d399; border: 1px solid rgba(0,184,148,0.35); }
    .badge-resources { background: rgba(9, 132, 227, 0.15);  color: #60a5fa; border: 1px solid rgba(9,132,227,0.35); }
    .badge-archives  { background: rgba(99, 110, 114, 0.18); color: #94a3b8; border: 1px solid rgba(99,110,114,0.35); }

    /* Tags */
    .tag-chip {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 11px;
        font-weight: 500;
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        color: #94a3b8;
        margin-right: 4px;
    }
    
    /* Glass card */
    .glass-card {
        background: rgba(255,255,255,0.03);
        backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 1.5rem;
    }
    
    /* Chat UI fixes */
    .stChatInput {
        background: transparent !important;
        border: none !important;
    }
    
    /* Small stats bar under graph */
    .mini-stat {
        text-align: center;
        background: rgba(255,255,255,0.03);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 8px;
        padding: 8px;
    }
    .mini-stat h3 { font-size: 1.2rem; margin:0; padding:0; color:#e2e8f0; }
    .mini-stat p { font-size: 0.7rem; margin:0; color:#94a3b8; text-transform:uppercase; }
</style>
""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════════
#  MODALS
# ═══════════════════════════════════════════════════════════════════════════════

@st.dialog("✦ Capture Knowledge")
def capture_modal():
    tab1, tab2 = st.tabs(["📝 Note", "🔗 URL"])
    
    with tab1:
        note_text = st.text_area("Your note", height=150, placeholder="Type or paste your note here…", label_visibility="collapsed")
        if st.button("Capture Note", use_container_width=True, type="primary"):
            if note_text.strip():
                with st.spinner("Processing..."):
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
                        st.session_state["graph_trigger"] = time.time()  # Force graph refresh
                        st.success(f"Captured: {classification.suggested_title}")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    with tab2:
        url_input = st.text_input("URL", placeholder="https://...", label_visibility="collapsed")
        if st.button("Capture URL", use_container_width=True, type="primary"):
            if url_input.strip():
                with st.spinner("Processing..."):
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
                        st.session_state["graph_trigger"] = time.time()
                        st.success(f"Captured: {classification.suggested_title}")
                        time.sleep(1.5)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

# ═══════════════════════════════════════════════════════════════════════════════
#  TOP HEADER
# ═══════════════════════════════════════════════════════════════════════════════

wiki_count = sum(1 for _ in WIKI_DIR.rglob("*.md")) if WIKI_DIR.exists() else 0
try: embedded_count = get_engine().collection.count()
except: embedded_count = 0

header_html = f'''
<div class="app-header-container">
    <div class="logo-container">
        <span style="font-size:22px; filter: drop-shadow(0 0 8px rgba(108,92,231,0.6));">🧠</span>
        <span>ASHISH'S BRaIN</span>
    </div>
    <div style="display:flex; gap:15px; align-items:center;">
        <div class="stats-pill">
            <span>◈ {wiki_count} notes</span>
            <span style="opacity:0.3">·</span>
            <span>⚡ {embedded_count} embedded</span>
        </div>
    </div>
</div>
'''
st.markdown(header_html, unsafe_allow_html=True)

# We use absolute positioning hack for the capture button since st.button can't be easily put inside custom HTML.
colA, colB = st.columns([8.5, 1.5])
with colB:
    st.markdown('<div style="margin-top:-65px;"></div>', unsafe_allow_html=True)
    if st.button("✦ Capture", use_container_width=True, type="primary"):
        capture_modal()

# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN SPLIT PANE
# ═══════════════════════════════════════════════════════════════════════════════

if "selected_node_id" not in st.session_state:
    st.session_state["selected_node_id"] = None

col_left, col_right = st.columns([7, 3], gap="large")

with col_left:
    graph_data = _get_graph_data()
    nodes_data = graph_data.get("nodes", [])
    edges_data = graph_data.get("edges", [])
    
    if not nodes_data:
        st.markdown('''
        <div style="text-align:center; padding: 100px; color:#94a3b8;">
            <div style="font-size: 50px;">🌱</div>
            <h2>Your second brain is empty</h2>
            <p>Click <b>✦ Capture</b> in the top right to add your first note.</p>
        </div>
        ''', unsafe_allow_html=True)
    else:
        node_lookup = {n["id"]: n for n in nodes_data}
        highlight_ids = st.session_state.get("highlight_source_ids", [])
        
        ag_nodes = []
        for n in nodes_data:
            cat = n.get("category", "resources")
            size = max(15, min(45, 15 + n.get("link_count", 0) * 6))
            color = CATEGORY_COLORS.get(cat, "#0984E3")
            
            if highlight_ids:
                if n["id"] in highlight_ids:
                    color = "#a78bfa"
                    size = size * 1.3
                else:
                    color = "rgba(255,255,255,0.1)"
                    
            ag_nodes.append(Node(
                id=n["id"], label=n.get("label", n["id"][:12]), size=size, color=color,
                title=f"{n.get('label', '')}\\n\\n{n.get('summary', '')}", font={"color": "#e2e8f0", "size": 11}
            ))
            
        ag_edges = [Edge(source=e["from"], target=e["to"], color="rgba(148,163,184,0.2)", width=1.5) for e in edges_data]
        config = Config(width="100%", height=500, directed=False, physics={"barnesHut": {"gravitationalConstant": -3000, "springLength": 120, "springConstant": 0.04}}, nodeHighlightBehavior=True, highlightColor="#6C5CE7")
        
        selected = agraph(nodes=ag_nodes, edges=ag_edges, config=config)
        if selected: st.session_state["selected_node_id"] = selected
            
        cats = {"projects": 0, "areas": 0, "resources": 0, "archives": 0}
        for n in nodes_data: cats[n.get("category", "resources")] += 1
        
        st.markdown("<br>", unsafe_allow_html=True)
        s_cols = st.columns(5)
        for i, cat in enumerate(["projects", "areas", "resources", "archives"]):
            with s_cols[i]: st.markdown(f'<div class="mini-stat"><h3>{cats[cat]}</h3><p style="color:{CATEGORY_COLORS[cat]}">{cat}</p></div>', unsafe_allow_html=True)
        with s_cols[4]: st.markdown(f'<div class="mini-stat"><h3>{len(nodes_data)}</h3><p>Total</p></div>', unsafe_allow_html=True)

with col_right:
    st.markdown("### Note Details")
    sel_id = st.session_state.get("selected_node_id")
    if not sel_id or sel_id not in node_lookup:
        st.markdown('''
        <div style="text-align:center; padding: 40px 20px; color:#94a3b8; background:rgba(255,255,255,0.02); border-radius:12px; border:1px solid rgba(255,255,255,0.05);">
            <div style="font-size:30px; margin-bottom:10px;">◎</div>
            <p>Click a node in the graph<br>to explore its content.</p>
        </div>
        ''', unsafe_allow_html=True)
    else:
        node = node_lookup[sel_id]
        cat = node.get("category", "resources")
        badge_cls = f"badge-{cat}"
        st.markdown(f"#### {node.get('label', 'Untitled')}")
        tags_html = "".join([f'<span class="tag-chip">{t}</span>' for t in node.get("tags", [])])
        st.markdown(f'<span class="category-badge {badge_cls}">{cat}</span> &nbsp; {tags_html}', unsafe_allow_html=True)
        st.markdown("<hr style='border-color:rgba(255,255,255,0.1); margin:10px 0;'>", unsafe_allow_html=True)
        if node.get("summary"): st.markdown(f"*{node['summary']}*")
        if node.get("content_preview"): st.markdown(f'<div style="font-size:13px; color:#94a3b8; line-height:1.6;">{node["content_preview"]}</div>', unsafe_allow_html=True)
        wiki_file = _find_wiki_file(sel_id)
        if wiki_file:
            with st.expander("📖 Full Content"):
                meta = _parse_note_meta(wiki_file)
                st.markdown(meta.get("body", ""))

# ═══════════════════════════════════════════════════════════════════════════════
#  ASK BAR (CHAT)
# ═══════════════════════════════════════════════════════════════════════════════

if "chat_history" not in st.session_state:
    st.session_state["chat_history"] = []

st.markdown("<br><br><br>", unsafe_allow_html=True)

if st.session_state.chat_history:
    last_msg = st.session_state.chat_history[-1]
    if last_msg["role"] == "assistant":
        with st.container():
            confColor = {"high": "#34d399", "medium": "#fbbf24", "low": "#f87171"}.get(last_msg.get("confidence", "low"), "#94a3b8")
            st.markdown(f'''
            <div class="glass-card" style="margin-bottom:10px;">
                <div style="font-size:11px; color:#94a3b8; margin-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.1); padding-bottom:5px;">
                    <em>"{st.session_state.chat_history[-2]['content']}"</em>
                    <span style="float:right; color:{confColor}; font-weight:bold;">{last_msg.get("confidence", "").upper()} CONFIDENCE</span>
                </div>
                <div>{last_msg["content"]}</div>
            </div>
            ''', unsafe_allow_html=True)
            
            if last_msg.get("sources"):
                cols = st.columns(len(last_msg["sources"]) + 1)
                cols[0].markdown("**Sources:**")
                for i, src in enumerate(last_msg["sources"]):
                    if cols[i+1].button(f"{src['title']} ({int(src['similarity']*100)}%)", key=f"src_{i}_{time.time()}"):
                        st.session_state["highlight_source_ids"] = [s["id"] for s in last_msg["sources"]]
                        st.rerun()
                        
question = st.chat_input("Ask your second brain anything...")
if question:
    st.session_state.chat_history.append({"role": "user", "content": question})
    st.session_state["highlight_source_ids"] = []
    
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
                "confidence": res.confidence
            })
            
            if sources_data:
                st.session_state["highlight_source_ids"] = [s["id"] for s in sources_data]
                
            st.rerun()
        except Exception as e:
            st.error(f"Error: {e}")
