"""
SecondSelf — Central Configuration

All shared paths, constants, and settings used across the application.
"""

from pathlib import Path

# ─── Paths ───────────────────────────────────────────────────────────
# PROJECT_ROOT resolves to the top-level project directory.
# __file__ is src/secondself/config.py → .parent.parent.parent = project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

RAW_DIR = PROJECT_ROOT / "raw"
WIKI_DIR = PROJECT_ROOT / "wiki"
DATA_DIR = PROJECT_ROOT / "data"
CHROMA_DIR = DATA_DIR / "chroma"
GRAPH_JSON = DATA_DIR / "graph.json"
INDEX_JSON = DATA_DIR / "index.json"
WEB_DIR = PROJECT_ROOT / "web"

# ─── PARA Categories ────────────────────────────────────────────────
PARA_CATEGORIES = ["projects", "areas", "resources", "archives"]

# ─── Embedding ───────────────────────────────────────────────────────
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# ─── Linking ─────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.65
MAX_LINKS_PER_NOTE = 5
TOP_K_RETRIEVAL = 5

# ─── LLM ─────────────────────────────────────────────────────────────
LLM_PROVIDER = "groq"
LLM_MODEL = "llama3-70b-8192"

# ─── Server ──────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8000


def ensure_dirs() -> None:
    """Create all required directories if they don't exist."""
    dirs = [
        RAW_DIR,
        DATA_DIR,
        CHROMA_DIR,
        WEB_DIR,
    ]
    # Add PARA wiki subdirectories
    for category in PARA_CATEGORIES:
        dirs.append(WIKI_DIR / category)

    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)


# Auto-create directories on first import
ensure_dirs()
