"""
SecondSelf — Streamlit Cloud Deployment Readiness Validator

Run: python validate_deploy.py
"""

import sys
import os
import json
from pathlib import Path

# Simulate Streamlit Cloud: CWD = repo root
os.chdir(Path(__file__).resolve().parent)
sys.path.insert(0, "src")

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

errors = []
warnings = []


def check(condition, msg, is_warning=False):
    if condition:
        print(f"  {PASS} {msg}")
    elif is_warning:
        print(f"  {WARN} {msg}")
        warnings.append(msg)
    else:
        print(f"  {FAIL} {msg}")
        errors.append(msg)


print("\n═══ SecondSelf Deployment Readiness Check ═══\n")

# ── 1. Required files ──────────────────────────────────────────────────────
print("1. Required Files")
root = Path(".")
check((root / "streamlit_app.py").exists(), "streamlit_app.py exists")
check((root / "requirements.txt").exists(), "requirements.txt exists")
check((root / "runtime.txt").exists(), "runtime.txt exists")
check((root / "pyproject.toml").exists(), "pyproject.toml exists")
check((root / "packages.txt").exists(), "packages.txt exists")
check((root / ".streamlit" / "config.toml").exists(), ".streamlit/config.toml exists")
check((root / "src" / "secondself" / "__init__.py").exists(), "src/secondself/__init__.py exists")

# ── 2. runtime.txt ─────────────────────────────────────────────────────────
print("\n2. Runtime")
rt = (root / "runtime.txt").read_text().strip()
check(rt.startswith("python-3.1"), f"runtime.txt = '{rt}' (Python 3.1x)")

# ── 3. requirements.txt ───────────────────────────────────────────────────
print("\n3. Requirements")
req_text = (root / "requirements.txt").read_text()
check("-e ." not in req_text, "No editable install (-e .) — would fail on Cloud")
check("streamlit" in req_text, "streamlit listed")
check("streamlit-agraph" in req_text, "streamlit-agraph listed")
check("sentence-transformers" in req_text, "sentence-transformers listed")
check("chromadb" in req_text, "chromadb listed")
check("groq" in req_text, "groq listed")
check("hatchling" in req_text, "hatchling (build backend) listed")
# Heavy deps should NOT be in requirements.txt
check("whisper" not in req_text, "openai-whisper NOT in requirements (too heavy)")
check("easyocr" not in req_text, "easyocr NOT in requirements (too heavy)")
check("moviepy" not in req_text, "moviepy NOT in requirements (too heavy)")

# ── 4. pyproject.toml ─────────────────────────────────────────────────────
print("\n4. pyproject.toml")
pp_text = (root / "pyproject.toml").read_text()
check("[project.optional-dependencies]" in pp_text, "Heavy deps moved to optional-dependencies")
check("[build-system]" in pp_text, "build-system section present")
check("hatchling" in pp_text, "hatchling build backend specified")

# ── 5. packages.txt ───────────────────────────────────────────────────────
print("\n5. System Packages")
pkg_text = (root / "packages.txt").read_text()
check("build-essential" in pkg_text, "build-essential listed (needed for chromadb C ext)")

# ── 6. Streamlit config ──────────────────────────────────────────────────
print("\n6. Streamlit Config")
cfg_text = (root / ".streamlit" / "config.toml").read_text()
check("[theme]" in cfg_text, "[theme] section present")
check("[server]" in cfg_text, "[server] section present")
check("headless = true" in cfg_text, "headless = true (required for Cloud)")
check("[browser]" in cfg_text, "[browser] section present")

# ── 7. Import chain ──────────────────────────────────────────────────────
print("\n7. Import Chain (simulating Streamlit Cloud)")
try:
    from secondself.config import (
        PROJECT_ROOT, WIKI_DIR, RAW_DIR, DATA_DIR,
        CHROMA_DIR, GRAPH_JSON, PARA_CATEGORIES,
    )
    check(True, f"secondself.config imports OK — root={PROJECT_ROOT}")
    check(PARA_CATEGORIES == ["projects", "areas", "resources", "archives"],
          f"PARA_CATEGORIES = {PARA_CATEGORIES}")
except Exception as e:
    check(False, f"secondself.config import failed: {e}")

try:
    from secondself.graph_builder import build_graph, export_graph
    check(True, "secondself.graph_builder imports OK")
except Exception as e:
    check(False, f"secondself.graph_builder import failed: {e}")

try:
    from secondself.classify import classify_capture, ClassificationResult
    check(True, "secondself.classify imports OK")
except Exception as e:
    check(False, f"secondself.classify import failed: {e}")

try:
    from secondself.capture import capture_note, capture_url
    check(True, "secondself.capture imports OK")
except Exception as e:
    check(False, f"secondself.capture import failed: {e}")

try:
    from secondself.wiki_writer import write_wiki_note
    check(True, "secondself.wiki_writer imports OK")
except Exception as e:
    check(False, f"secondself.wiki_writer import failed: {e}")

try:
    from secondself.linker import find_related, update_backlinks
    check(True, "secondself.linker imports OK")
except Exception as e:
    check(False, f"secondself.linker import failed: {e}")

try:
    from secondself.embed import EmbeddingEngine
    check(True, "secondself.embed imports OK (EmbeddingEngine class found)")
except Exception as e:
    check(False, f"secondself.embed import failed: {e}")

try:
    from secondself.ask import ask, AskResponse
    check(True, "secondself.ask imports OK")
except Exception as e:
    check(False, f"secondself.ask import failed: {e}")

# ── 8. Streamlit app syntax check ────────────────────────────────────────
print("\n8. Streamlit App Syntax")
try:
    import py_compile
    py_compile.compile("streamlit_app.py", doraise=True)
    check(True, "streamlit_app.py compiles without syntax errors")
except py_compile.PyCompileError as e:
    check(False, f"streamlit_app.py has syntax errors: {e}")

# ── 9. Secrets bridge ────────────────────────────────────────────────────
print("\n9. Secrets Handling")
app_code = (root / "streamlit_app.py").read_text()
check("st.secrets" in app_code, "st.secrets bridge present in streamlit_app.py")
check("GROQ_API_KEY" in app_code, "GROQ_API_KEY referenced in app")
secrets_example = (root / ".streamlit" / "secrets.toml.example")
check(secrets_example.exists(), ".streamlit/secrets.toml.example exists")

# ── 10. .gitignore check ────────────────────────────────────────────────
print("\n10. Git Safety")
gi = (root / ".gitignore").read_text()
check(".env" in gi, ".env is gitignored (secrets safe)")
check("secrets.toml" in gi, "secrets.toml is gitignored")
check("__pycache__" in gi, "__pycache__ is gitignored")
check("data/" in gi or "data/chroma/" in gi, "data/ is gitignored", is_warning=True)
check("wiki/" in gi, "wiki/ is gitignored (empty brain on deploy)", is_warning=True)

# ── Summary ──────────────────────────────────────────────────────────────
print("\n" + "═" * 50)
if errors:
    print(f"\n{FAIL} {len(errors)} ERROR(S) found — fix before deploying:")
    for e in errors:
        print(f"   • {e}")
else:
    print(f"\n{PASS} All checks passed!")

if warnings:
    print(f"\n{WARN} {len(warnings)} warning(s):")
    for w in warnings:
        print(f"   • {w}")

print()
sys.exit(1 if errors else 0)
