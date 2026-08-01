"""
SecondSelf — Central Configuration

All shared paths, constants, and settings used across the application.
"""

import os
from pathlib import Path


# ─── Paths ───────────────────────────────────────────────────────────

def _resolve_project_root() -> Path:
    """Find the project root directory.

    Resolution order:
      1. SECONDSELF_ROOT env-var (explicit override for any deployment).
      2. __file__-based: works when running from the source tree
         (i.e. ``src/secondself/config.py`` → parent×3 = project root).
      3. CWD fallback: on Streamlit Cloud the package is pip-installed
         into site-packages, so __file__ is NOT in the source tree.
         Streamlit Cloud sets CWD to the cloned repo root, so CWD works.
    """
    # 1. Explicit env-var
    env_root = os.environ.get("SECONDSELF_ROOT")
    if env_root:
        return Path(env_root)

    # 2. __file__-based (local dev: src/secondself/config.py → ../../..)
    file_root = Path(__file__).resolve().parent.parent.parent
    if (file_root / "src" / "secondself").is_dir():
        return file_root

    # 3. CWD fallback (Streamlit Cloud: CWD = /mount/src/<repo>/)
    cwd = Path.cwd()
    if (cwd / "src" / "secondself").is_dir() or (cwd / "raw").is_dir():
        return cwd

    # Last resort: use __file__-based even if it doesn't look right
    return file_root


PROJECT_ROOT = _resolve_project_root()

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
SIMILARITY_THRESHOLD = 0.40
MAX_LINKS_PER_NOTE = 5
TOP_K_RETRIEVAL = 5

# ─── LLM ─────────────────────────────────────────────────────────────
LLM_PROVIDER = "groq"
LLM_MODEL = "llama-3.3-70b-versatile"

# ─── Server ──────────────────────────────────────────────────────────
HOST = "0.0.0.0"
PORT = 8000


def ensure_dirs() -> None:
    """Create all required directories if they don't exist.

    Silently skips directories that can't be created (e.g. on read-only
    filesystems in cloud deployments).
    """
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
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # Read-only filesystem — skip gracefully


# Auto-create directories on first import
ensure_dirs()

