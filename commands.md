# 🧠 SecondSelf — Complete Command Reference

> **Legend:**  ✅ Available now &nbsp;|&nbsp; 🔜 Coming in a later phase &nbsp;|&nbsp; 🐍 Python-only (no CLI yet)

---

## Table of Contents

1. [Environment & Setup](#1-environment--setup)
2. [Phase 1 — Capture (The Archivist)](#2-phase-1--capture-the-archivist)
3. [Phase 2 — Process & Organize (The Librarian)](#3-phase-2--process--organize-the-librarian)
4. [Phase 3 — Visualize (The Cartographer)](#4-phase-3--visualize-the-cartographer)
5. [Phase 4 — Ask & Deploy (The Oracle)](#5-phase-4--ask--deploy-the-oracle)
6. [Developer & Debug Commands](#6-developer--debug-commands)

---

## 1. Environment & Setup

### Install dependencies
```bash
uv sync
```

### Verify Python environment
```bash
uv run python --version
```

### Verify config paths resolve correctly
```bash
uv run python -c "
from secondself.config import RAW_DIR, WIKI_DIR, DATA_DIR, CHROMA_DIR
print('RAW_DIR   :', RAW_DIR)
print('WIKI_DIR  :', WIKI_DIR)
print('DATA_DIR  :', DATA_DIR)
print('CHROMA_DIR:', CHROMA_DIR)
"
```

### Check project version ✅
```bash
uv run secondself --version
```

### Show all available CLI commands ✅
```bash
uv run secondself --help
```

---

## 2. Phase 1 — Capture (The Archivist)

> **Status:** ✅ Fully implemented

### 2.1 Capture a text note ✅
```bash
uv run secondself capture note "Your note text here"
```

**Examples:**
```bash
uv run secondself capture note "Attention is all you need — transformers replace RNNs with self-attention"

uv run secondself capture note "PARA method: Projects, Areas, Resources, Archives for organizing knowledge"

uv run secondself capture note "The Feynman Technique: explain a concept in simple terms to understand it deeply"
```

---

### 2.2 Capture a URL ✅
```bash
uv run secondself capture url "https://example.com"
```

**Examples:**
```bash
uv run secondself capture url "https://arxiv.org/abs/1706.03762"

uv run secondself capture url "https://www.paulgraham.com/greatwork.html"

uv run secondself capture url "https://docs.python.org/3/library/pathlib.html"
```

---

### 2.3 Capture a file ✅
```bash
uv run secondself capture file "path/to/your/file.pdf"
uv run secondself capture file "path/to/your/notes.txt"
uv run secondself capture file "path/to/script.py"
```

**Supported file types:**
| Extension | Extraction Method |
|---|---|
| `.txt`, `.md`, `.py`, `.js`, etc. | Read directly |
| `.pdf` | PyMuPDF text extraction |
| Other (binary) | Stores filename + note |

---

### 2.4 List all captured items ✅
```bash
uv run secondself list
```
Displays a table: `ID | Type | Title/Preview | Timestamp`

---

### 2.5 Show a specific capture ✅
```bash
uv run secondself show <capture_id>
```

**Examples:**
```bash
# Use the first 8 characters of any ID shown in `list`
uv run secondself show 509de5df
uv run secondself show 58a6baa7
uv run secondself show 931701ce
```
Displays full metadata, content preview, and raw JSON.

---

## 3. Phase 2 — Process & Organize (The Librarian)

### 3.1 Classify a piece of content with AI 🐍 ✅
```bash
uv run python -c "
from secondself.classify import classify
result = classify('Your content to classify here')
print('Category      :', result.category)
print('Title         :', result.suggested_title)
print('Summary       :', result.summary)
print('Tags          :', result.tags)
print('Confidence    :', result.confidence)
"
```

### 3.2 Classify a raw capture by ID 🐍 ✅
```bash
uv run python -c "
from secondself.capture import get_capture
from secondself.classify import classify_capture
cap = get_capture('509de5df')          # replace with your capture ID
result = classify_capture(cap)
print(result.category, '|', result.suggested_title)
"
```

### 3.3 Classify all captures in raw/ 🐍 ✅
```bash
uv run python -c "
from secondself.capture import list_captures
from secondself.classify import classify_capture
for cap in list_captures():
    result = classify_capture(cap)
    print(cap['id'][:8], '->', result.category, '|', result.suggested_title)
"
```

---

### 3.4 Initialize the Embedding Engine 🐍 ✅
```bash
uv run python -c "
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
print('Collection name :', e.collection.name)
print('Notes stored    :', e.collection.count())
"
```
> **Note:** First run downloads the `all-MiniLM-L6-v2` model (~90 MB). One-time only.

### 3.5 Embed and store a note in ChromaDB 🐍 ✅
```bash
uv run python -c "
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
e.store(
    'my-capture-id',
    'The text content to embed and store',
    {
        'category': 'resources',
        'tags': '[\"ai\", \"nlp\"]',
        'title': 'My Note Title',
        'timestamp': '2026-07-15T10:00:00Z',
    }
)
print('Stored. Total notes:', e.collection.count())
"
```

### 3.6 Query semantically similar notes 🐍 ✅
```bash
uv run python -c "
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
results = e.query_similar('machine learning neural networks', k=5)
for r in results:
    print(r['id'][:8], 'sim='+str(round(r['similarity'],3)), r['metadata'].get('title',''))
"
```

### 3.7 Find notes similar to an existing note by ID 🐍 ✅
```bash
uv run python -c "
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
results = e.query_similar_by_id('your-capture-id', k=5)
for r in results:
    print(r['id'][:8], 'sim='+str(round(r['similarity'],3)), r['metadata'].get('title',''))
"
```

### 3.8 Check how many notes are in ChromaDB 🐍 ✅
```bash
uv run python -c "
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
print('Notes in ChromaDB:', e.collection.count())
"
```

---

### 3.9 Auto-link related notes 🔜  *(Step 2.3 — linker.py)*
```bash
# Coming after linker.py is implemented
uv run secondself process <capture_id>
```

### 3.10 Process ALL captures (classify + embed + link + write wiki) 🔜  *(Step 2.5)*
```bash
uv run secondself process
```

### 3.11 Re-process everything from scratch 🔜  *(Step 2.5)*
```bash
uv run secondself reprocess
```

### 3.12 Semantic search over your knowledge base 🔜  *(Step 2.5)*
```bash
uv run secondself search "your query here"

# Examples:
uv run secondself search "machine learning"
uv run secondself search "productivity systems"
uv run secondself search "transformer architecture"
```

---

## 4. Phase 3 — Visualize (The Cartographer)

> **Status:** 🔜 Not yet implemented (Step 3.x)

### 4.1 Build the knowledge graph JSON 🔜
```bash
uv run secondself graph
# Outputs: data/graph.json with nodes + edges
```

### 4.2 Launch the web UI 🔜
```bash
uv run secondself serve
# Opens: http://localhost:8000
```

### 4.3 View the interactive graph in browser 🔜
```
http://localhost:8000
```

---

## 5. Phase 4 — Ask & Deploy (The Oracle)

> **Status:** 🔜 Not yet implemented (Step 4.x)

### 5.1 Ask a natural-language question over your notes 🔜
```bash
uv run secondself ask "What do I know about transformers?"
uv run secondself ask "What productivity techniques have I captured?"
uv run secondself ask "Summarize my notes on machine learning"
uv run secondself ask "What are the most important concepts I have studied?"
```

### 5.2 Launch the full web app (graph + chat) 🔜
```bash
uv run secondself serve
# Accessible at http://localhost:8000
```

---

## 6. Developer & Debug Commands

### Run all tests
```bash
uv run pytest
uv run pytest -v                 # verbose output
uv run pytest -v --tb=short      # short tracebacks
```

### Run a specific test file
```bash
uv run pytest tests/test_capture.py -v
```

### Inspect raw capture JSON files (PowerShell)
```powershell
# List all JSON files in raw/
Get-ChildItem raw\*.json

# Pretty-print a specific capture
Get-Content raw\20260715_509de5df.json | python -m json.tool
```

### List wiki notes after Phase 2 (PowerShell)
```powershell
Get-ChildItem wiki\ -Recurse -Filter *.md
tree wiki\
```

### Inspect all ChromaDB contents 🐍
```bash
uv run python -c "
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
all_items = e.collection.get(include=['documents','metadatas'])
for id_, doc, meta in zip(all_items['ids'], all_items['documents'], all_items['metadatas']):
    print(id_[:8], meta.get('title','?'), '|', doc[:50])
"
```

### Clear ChromaDB (reset all embeddings) 🐍
```bash
uv run python -c "
import shutil
from secondself.config import CHROMA_DIR
shutil.rmtree(CHROMA_DIR, ignore_errors=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)
print('ChromaDB cleared.')
"
```

### Full pipeline test: Capture → Classify → Embed 🐍
```bash
uv run python -c "
from secondself.capture import list_captures
from secondself.classify import classify_capture
from secondself.embed import EmbeddingEngine

engine = EmbeddingEngine()
captures = list_captures()

for cap in captures:
    text = (cap.get('content', {}).get('text')
            or cap.get('content', {}).get('file_content', ''))
    result = classify_capture(cap)
    engine.store(cap['id'], text, {
        'category': result.category,
        'tags': str(result.tags),
        'title': result.suggested_title,
        'timestamp': cap.get('timestamp', ''),
    })
    print('OK', cap['id'][:8], '->', result.category, '|', result.suggested_title)

print()
print('Total in ChromaDB:', engine.collection.count())
"
```

---

## Quick Reference Card

| Command | Status | What it does |
|---|---|---|
| `secondself --version` | ✅ | Show version |
| `secondself --help` | ✅ | List all commands |
| `secondself capture note "..."` | ✅ | Capture a text note |
| `secondself capture url "..."` | ✅ | Capture a URL |
| `secondself capture file <path>` | ✅ | Capture a file |
| `secondself list` | ✅ | List all captures |
| `secondself show <id>` | ✅ | Show capture details |
| `secondself process` | 🔜 | Classify + embed + link all captures |
| `secondself process <id>` | 🔜 | Process a single capture |
| `secondself reprocess` | 🔜 | Re-process everything from scratch |
| `secondself search "..."` | 🔜 | Semantic search over wiki |
| `secondself graph` | 🔜 | Build knowledge graph JSON |
| `secondself serve` | 🔜 | Launch web UI (graph + notes + chat) |
| `secondself ask "..."` | 🔜 | Ask AI a question over your notes |
