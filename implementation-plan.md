# SecondSelf — Phase-Wise Implementation Plan

A step-by-step execution plan for building the SecondSelf AI Second Brain, organized by weekly phases. Each phase is self-contained with clear inputs, outputs, implementation steps, file-by-file breakdowns, and acceptance criteria pulled directly from the problem statement.

---

## Prerequisites & One-Time Setup

Before starting any phase, complete this foundational setup:

### Step 0.1 — Environment

| Item | Action |
|---|---|
| **Python** | Verify Python 3.11+ installed (`python --version`) |
| **uv** | Install uv package manager (`pip install uv`) |
| **Git** | Initialize repo (`git init`) |
| **Groq API Key** | Sign up at [console.groq.com](https://console.groq.com), generate free API key |

### Step 0.2 — Project Scaffold

Create the base directory structure and configuration files:

```
Action: Create these files
├── pyproject.toml          # Dependencies + CLI entry point
├── .env                    # GROQ_API_KEY=your_key_here
├── .env.example            # Template (committed to git)
├── .gitignore              # Python, .env, data/chroma/
├── README.md               # Project overview
├── architecture.md         # System architecture reference
│
├── raw/                    # Create empty directory
│   └── .gitkeep
├── wiki/                   # Create with PARA subdirs
│   ├── projects/.gitkeep
│   ├── areas/.gitkeep
│   ├── resources/.gitkeep
│   └── archives/.gitkeep
├── data/                   # Create empty directory
│   └── .gitkeep
├── src/secondself/
│   ├── __init__.py         # Package init (version string)
│   └── config.py           # Central configuration
├── web/                    # Create empty directory
│   └── .gitkeep
└── tests/
    └── __init__.py
```

### Step 0.3 — Install Dependencies

```bash
uv sync
```

### Step 0.4 — Verify Setup

```bash
python -c "from secondself.config import RAW_DIR; print(RAW_DIR)"
```

**Checkpoint:** All directories exist, `uv sync` succeeds, config imports work.

---

## Phase 1: The Archivist — "Capture Everything, Lose Nothing"

> **Badge:** 🏛️ The Archivist  
> **Duration:** Week 1  
> **Goal:** One command captures anything into `raw/` with timestamp + unique ID.

### Input
- Empty `raw/` directory
- User's scattered notes, links, and files

### Output
- Working CLI tool (`secondself capture ...`)
- `raw/` populated with 10+ real captured items as immutable JSON

---

### Step 1.1 — Implement `config.py`

**File:** `src/secondself/config.py`

Central configuration shared by all modules:

```python
# What to implement:
- PROJECT_ROOT path resolution (relative to this file)
- RAW_DIR, WIKI_DIR, DATA_DIR, CHROMA_DIR paths
- GRAPH_JSON, INDEX_JSON, WEB_DIR paths
- PARA_CATEGORIES list
- EMBEDDING_MODEL, EMBEDDING_DIM constants
- SIMILARITY_THRESHOLD, MAX_LINKS_PER_NOTE, TOP_K_RETRIEVAL
- LLM_PROVIDER, LLM_MODEL
- HOST, PORT for server
- ensure_dirs() function that creates all dirs on import
```

**Test:** Import config, verify all paths resolve correctly.

---

### Step 1.2 — Implement `capture.py`

**File:** `src/secondself/capture.py`

Core capture logic — three functions for three capture types:

```python
# Functions to implement:

def capture_note(text: str) -> dict:
    """Capture a plain text note."""
    # 1. Generate UUID (uuid4)
    # 2. Generate ISO timestamp
    # 3. Build JSON document with id, timestamp, type="note", content.text
    # 4. Compute metadata (word_count, char_count, auto-title from first N words)
    # 5. Write to raw/{YYYYMMDD}_{8-char-uuid}.json
    # 6. Return the capture dict

def capture_url(url: str) -> dict:
    """Capture a URL with fetched title and description."""
    # 1. Generate UUID + timestamp
    # 2. HTTP GET the URL (httpx, timeout=10s)
    # 3. Extract <title> and <meta name="description"> from HTML
    # 4. Build JSON with type="url", content.url, content.text (title + desc)
    # 5. Handle fetch failures gracefully (store URL even if fetch fails)
    # 6. Write to raw/
    # 7. Return capture dict

def capture_file(file_path: str) -> dict:
    """Capture a file with extracted text content."""
    # 1. Generate UUID + timestamp
    # 2. Validate file exists
    # 3. Extract text based on extension:
    #    - .txt, .md, .py, .js, etc. → read directly
    #    - .pdf → pymupdf text extraction
    #    - other → store filename + "binary file" note
    # 4. Build JSON with type="file", content.file_path, content.file_content
    # 5. Write to raw/
    # 6. Return capture dict

def list_captures() -> list[dict]:
    """List all captures in raw/, sorted by timestamp."""

def get_capture(capture_id: str) -> dict | None:
    """Retrieve a specific capture by ID (prefix match)."""
```

**Key details:**
- Filename format: `{YYYYMMDD}_{first-8-chars-of-uuid}.json`
- JSON is written with `indent=2` for readability
- Never modify a file once written (immutability)
- Use `rich` console for colorful output

---

### Step 1.3 — Implement `cli.py`

**File:** `src/secondself/cli.py`

Click-based CLI with command groups:

```python
# Commands to implement:

@click.group()
def main():
    """🧠 SecondSelf — Your Personal AI Second Brain"""

@main.group()
def capture():
    """Capture a note, URL, or file."""

@capture.command()
@click.argument("text")
def note(text):
    """Capture a text note."""
    # Call capture_note(text)
    # Print success with rich formatting

@capture.command()
@click.argument("url")
def url(url):
    """Capture a URL."""
    # Call capture_url(url)
    # Print success with fetched title

@capture.command()
@click.argument("file_path", type=click.Path(exists=True))
def file(file_path):
    """Capture a file."""
    # Call capture_file(file_path)
    # Print success with filename

@main.command("list")
def list_cmd():
    """List all captured items."""
    # Call list_captures()
    # Print as rich table: ID | Type | Title/Preview | Timestamp

@main.command()
@click.argument("capture_id")
def show(capture_id):
    """Show details of a specific capture."""
    # Call get_capture(capture_id)
    # Pretty-print the full JSON with rich
```

---

### Step 1.4 — Write Tests

**File:** `tests/test_capture.py`

```python
# Tests to implement:
- test_capture_note_creates_file()      # File exists in raw/ with correct structure
- test_capture_note_has_uuid()          # ID is valid UUID
- test_capture_note_has_timestamp()     # Timestamp is valid ISO format
- test_capture_url_fetches_title()      # URL capture includes fetched title
- test_capture_url_handles_failure()    # Bad URL still creates capture
- test_capture_file_extracts_text()     # Text file content is extracted
- test_capture_file_pdf()              # PDF text extraction works
- test_list_captures()                  # Returns all captures sorted by time
- test_get_capture_by_id()            # Prefix match works
- test_immutability()                  # Files are not modified after creation
```

---

### Step 1.5 — Capture 10+ Real Items

Use the CLI to capture your own real data:

```bash
secondself capture note "Attention is all you need — transformers replace RNNs with self-attention"
secondself capture url "https://arxiv.org/abs/1706.03762"
secondself capture note "PARA method: Projects, Areas, Resources, Archives for organizing knowledge"
secondself capture file "./some-real-document.pdf"
# ... capture 10+ total items
```

---

### Phase 1 Acceptance Criteria

| # | Criterion | How to Verify |
|---|---|---|
| 1 | `raw/` and `wiki/` folder structure exists | `ls raw/ wiki/` |
| 2 | One command captures a note, a link, AND a file | Run all three capture types |
| 3 | Every capture has a timestamp + unique ID | Inspect any JSON in `raw/` |
| 4 | 10+ real items captured | `secondself list` shows ≥ 10 items |

**Git checkpoint:** `git add . && git commit -m "Phase 1: The Archivist — capture pipeline complete"`

---

## Phase 2: The Librarian — "Teach AI to Organize For You"

> **Badge:** 📚 The Librarian  
> **Duration:** Week 2  
> **Goal:** AI auto-classifies with PARA, computes embeddings, and auto-links related notes.  
> **Depends on:** Phase 1 (raw captures exist)

### Input
- `raw/` with 10+ captured items from Phase 1

### Output
- Organized `wiki/` with PARA-categorized markdown notes
- ChromaDB vector store with all embeddings
- Bidirectional `[[links]]` between related notes
- 15+ real items processed

---

### Step 2.1 — Implement `classify.py`

**File:** `src/secondself/classify.py`

LLM-powered classification using Groq:

```python
# What to implement:

@dataclass
class ClassificationResult:
    category: str          # "projects" | "areas" | "resources" | "archives"
    tags: list[str]        # Up to 5 tags
    summary: str           # One-line summary
    suggested_title: str   # Short descriptive title
    confidence: float      # 0.0–1.0

def classify(content: str) -> ClassificationResult:
    """Send content to Groq LLM and get PARA classification."""
    # 1. Load GROQ_API_KEY from .env (python-dotenv)
    # 2. Build classification prompt (see architecture.md)
    # 3. Call Groq API with llama3-70b-8192
    # 4. Parse JSON response
    # 5. Validate category is one of PARA_CATEGORIES
    # 6. Return ClassificationResult
    # 7. Handle API errors gracefully (retry once, then raise)

def classify_capture(capture: dict) -> ClassificationResult:
    """Classify a raw capture dict."""
    # Extract text content from capture (handle note/url/file types)
    # Call classify() with the text
```

**Environment dependency:** Requires `GROQ_API_KEY` in `.env`

---

### Step 2.2 — Implement `embed.py`

**File:** `src/secondself/embed.py`

Embedding generation and ChromaDB storage:

```python
# What to implement:

class EmbeddingEngine:
    def __init__(self):
        # Load sentence-transformers model (all-MiniLM-L6-v2)
        # Initialize ChromaDB persistent client (data/chroma/)
        # Get or create collection "secondself_notes"

    def embed_text(self, text: str) -> list[float]:
        """Generate 384-dim embedding for text."""

    def store(self, capture_id: str, text: str, metadata: dict):
        """Embed text and store in ChromaDB with metadata."""
        # 1. Generate embedding
        # 2. Upsert into ChromaDB collection
        #    - id = capture_id
        #    - embedding = vector
        #    - document = text
        #    - metadata = {category, tags (JSON string), title, timestamp}

    def query_similar(self, text: str, k: int = 5) -> list[dict]:
        """Find k most similar notes to the given text."""
        # 1. Embed the query text
        # 2. Query ChromaDB collection
        # 3. Return list of {id, document, metadata, similarity}

    def query_similar_by_id(self, capture_id: str, k: int = 5) -> list[dict]:
        """Find k most similar notes to an existing note by ID."""
```

**First-run note:** The sentence-transformers model (~90MB) downloads on first use. This is a one-time operation.

---

### Step 2.3 — Implement `linker.py`

**File:** `src/secondself/linker.py`

Auto-linking via embedding similarity:

```python
# What to implement:

def find_related(capture_id: str, engine: EmbeddingEngine) -> list[dict]:
    """Find notes related to the given capture."""
    # 1. Query ChromaDB for top-K similar (K=5)
    # 2. Filter by SIMILARITY_THRESHOLD (≥ 0.65)
    # 3. Exclude self-match
    # 4. Return list of {id, title, similarity}

def insert_links(wiki_path: Path, related: list[dict]):
    """Insert [[wiki-links]] into a note's Related Notes section."""
    # 1. Read the markdown file
    # 2. Find or create "## Related Notes" section
    # 3. Add [[title]] links for each related note
    # 4. Cap at MAX_LINKS_PER_NOTE (5)
    # 5. Write back

def update_backlinks(wiki_dir: Path, source_title: str, related: list[dict]):
    """Add backlinks from related notes back to the source note."""
    # 1. For each related note, find its wiki file
    # 2. Add [[source_title]] to its Related Notes section
    # 3. Maintain bidirectionality
```

---

### Step 2.4 — Implement `wiki_writer.py`

**File:** `src/secondself/wiki_writer.py`

Transforms raw captures + classification into organized markdown:

```python
# What to implement:

def write_wiki_note(
    capture: dict,
    classification: ClassificationResult,
    related: list[dict]
) -> Path:
    """Create a markdown note in wiki/{category}/{slug}.md"""
    # 1. Generate slug from title (slugify: lowercase, hyphens, no special chars)
    # 2. Build YAML frontmatter (id, title, category, tags, created, source)
    # 3. Write markdown body:
    #    - # Title
    #    - Summary line
    #    - Original content
    #    - ## Related Notes section with [[links]]
    # 4. Place in wiki/{category}/{slug}.md
    # 5. Handle filename conflicts (append -2, -3, etc.)
    # 6. Return the file path

def slugify(text: str) -> str:
    """Convert title to filesystem-safe slug."""
```

---

### Step 2.5 — Add `process` Command to CLI

**File:** `src/secondself/cli.py` (extend)

```python
# New commands to add:

@main.command()
@click.argument("capture_id", required=False)
def process(capture_id):
    """Process raw captures: classify, embed, link, write to wiki."""
    # If capture_id given: process that one capture
    # If no capture_id: process ALL unprocessed captures
    #
    # For each capture:
    #   1. Read raw JSON
    #   2. Check if already processed (exists in wiki/)
    #   3. classify_capture() → ClassificationResult
    #   4. engine.store() → embed + store in ChromaDB
    #   5. find_related() → related notes
    #   6. write_wiki_note() → create markdown
    #   7. update_backlinks() → bidirectional links
    #   8. Print progress with rich

@main.command()
def reprocess():
    """Re-classify and re-link all captures from scratch."""
    # Clear wiki/ and ChromaDB
    # Process all raw captures

@main.command()
@click.argument("query")
def search(query):
    """Semantic search over your knowledge base."""
    # 1. engine.query_similar(query, k=5)
    # 2. Print results as rich table with scores
```

---

### Step 2.6 — Write Tests

**Files:** `tests/test_classify.py`, `tests/test_embed.py`, `tests/test_linker.py`

```python
# test_classify.py:
- test_classify_returns_valid_para_category()
- test_classify_returns_tags()
- test_classify_returns_summary()
- test_classify_handles_empty_content()

# test_embed.py:
- test_embed_produces_384_dim_vector()
- test_store_and_retrieve()
- test_query_similar_returns_results()
- test_query_excludes_self()

# test_linker.py:
- test_find_related_respects_threshold()
- test_find_related_caps_at_max_links()
- test_insert_links_creates_section()
- test_backlinks_are_bidirectional()
```

---

### Step 2.7 — Process 15+ Real Items

```bash
# Capture 5 more items to reach 15+
secondself capture note "..."
secondself capture url "..."

# Process everything
secondself process

# Verify
secondself list
ls wiki/projects/ wiki/areas/ wiki/resources/ wiki/archives/
```

---

### Phase 2 Acceptance Criteria

| # | Criterion | How to Verify |
|---|---|---|
| 1 | Any raw capture → category + tags + summary automatically | `secondself process <id>` |
| 2 | PARA categorization working | Check `wiki/` subdirectories have files |
| 3 | Embeddings computed per note | `python -c "from secondself.embed import ...; print(len(engine.collection.get()['ids']))"` |
| 4 | Related notes auto-linked (no manual tagging) | Open any wiki note, check `## Related Notes` |
| 5 | Runs on 15+ real items → organized `wiki/` | `secondself list` shows ≥ 15, wiki has organized files |

**Git checkpoint:** `git add . && git commit -m "Phase 2: The Librarian — auto-classify + auto-link complete"`

---

## Phase 3: The Cartographer — "Visualize the Brain"

> **Badge:** 🗺️ The Cartographer  
> **Duration:** Week 3  
> **Goal:** Wiki becomes a live, interactive, hoverable force-directed graph.  
> **Depends on:** Phase 2 (organized wiki with links)

### Input
- `wiki/` with PARA-organized, interlinked markdown notes

### Output
- `data/graph.json` with nodes + edges
- Interactive graph in browser (hover, drag, zoom)
- Built from real notes, not dummy data

---

### Step 3.1 — Implement `graph_builder.py`

**File:** `src/secondself/graph_builder.py`

Parse wiki notes and build graph data:

```python
# What to implement:

def parse_wiki_note(file_path: Path) -> dict:
    """Parse a wiki markdown file into a node dict."""
    # 1. Read file
    # 2. Parse YAML frontmatter (id, title, category, tags, created)
    # 3. Extract content body (for preview)
    # 4. Parse ## Related Notes section → extract [[link]] targets
    # 5. Return node dict: {id, label, category, tags, summary, content_preview, created, word_count}

def build_graph(wiki_dir: Path) -> dict:
    """Build complete graph JSON from all wiki notes."""
    # 1. Scan all .md files in wiki/ recursively
    # 2. Parse each into a node
    # 3. Build edges from [[links]] (match link text to node labels)
    # 4. Compute link_count per node
    # 5. Build metadata (total_nodes, total_edges, category counts, generated_at)
    # 6. Return {nodes: [...], edges: [...], metadata: {...}}

def export_graph(wiki_dir: Path, output_path: Path):
    """Build graph and write to JSON file."""
    # 1. Call build_graph()
    # 2. Write to output_path with indent=2
```

Add CLI command:

```python
@main.command()
def graph():
    """Build the knowledge graph from wiki notes."""
    # Call export_graph()
    # Print stats (nodes, edges, categories)
```

---

### Step 3.2 — Build `web/index.html`

**File:** `web/index.html`

Main web page layout:

```
Structure:
- <head>: Title, meta tags, Google Fonts (Inter), link to style.css
- <body>:
  - Header bar: Logo + "SecondSelf" + Capture button
  - Main content (split pane):
    - Left: Graph canvas container (id="graph-container")
    - Right: Note detail panel (id="note-panel")
      - Title, category badge, tags
      - Content preview
      - Related notes list
  - Bottom bar: Ask input + answer display area
  - <script> tags: vis-network CDN, graph.js, chat.js
```

**CDN for vis-network:**
```html
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
```

---

### Step 3.3 — Build `web/style.css`

**File:** `web/style.css`

Dark mode design system with glassmorphism:

```css
/* Design tokens to implement: */
:root {
  --bg-primary: #0a0a1a;         /* Deep dark background */
  --bg-secondary: #12122a;       /* Card backgrounds */
  --bg-glass: rgba(255,255,255,0.05); /* Glassmorphism */
  --text-primary: #e2e8f0;
  --text-secondary: #94a3b8;
  --accent-projects: #6C5CE7;    /* Purple */
  --accent-areas: #00B894;       /* Green */
  --accent-resources: #0984E3;   /* Blue */
  --accent-archives: #636E72;    /* Gray */
  --border-glass: rgba(255,255,255,0.1);
  --font-family: 'Inter', sans-serif;
}

/* Components to style: */
- Body (dark bg, grid pattern, font)
- Header bar (glass effect, sticky)
- Split pane layout (CSS Grid, responsive)
- Graph container (full height, dark bg)
- Note detail panel (glass card, scrollable)
- Category badges (colored pills)
- Tag chips (outlined, small)
- Ask bar (bottom fixed, glass effect)
- Answer display (animated reveal)
- Scrollbar (custom dark theme)
- Hover/focus transitions (200ms ease)
- Responsive breakpoints (stack on mobile)
```

---

### Step 3.4 — Build `web/graph.js`

**File:** `web/graph.js`

vis-network graph rendering and interaction:

```javascript
// What to implement:

async function loadGraph() {
  // 1. fetch('/api/graph') → graph JSON
  // 2. Transform nodes for vis-network:
  //    - Set color by category (PARA color map)
  //    - Set size proportional to link_count (min: 15, max: 45)
  //    - Set label to node title
  //    - Set title (hover tooltip) to summary
  // 3. Transform edges:
  //    - Set width proportional to similarity
  //    - Set color with opacity based on similarity
  // 4. Configure vis-network options:
  //    - Physics: barnesHut, gravity: -3000, damping: 0.3
  //    - Interaction: hover: true, tooltipDelay: 100
  //    - Nodes: shape: 'dot', font: { color: '#e2e8f0' }
  // 5. Create new vis.Network(container, data, options)
}

function setupInteractions(network) {
  // 1. network.on('hoverNode') → show tooltip card
  // 2. network.on('click') → populate note detail panel
  // 3. network.on('doubleClick') → zoom to node
  // 4. Add breathing animation for recent nodes (CSS animation class)
}

function showNoteDetail(nodeId) {
  // 1. Find node data by ID
  // 2. Populate detail panel:
  //    - Title, category badge, tags
  //    - Full content preview
  //    - Related notes as clickable links
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', loadGraph);
```

---

### Step 3.5 — Write Tests

**File:** `tests/test_graph.py`

```python
# Tests to implement:
- test_parse_wiki_note_extracts_frontmatter()
- test_parse_wiki_note_extracts_links()
- test_build_graph_creates_nodes_for_all_notes()
- test_build_graph_creates_edges_from_links()
- test_edges_are_bidirectional()
- test_graph_metadata_has_correct_counts()
- test_export_graph_writes_valid_json()
```

---

### Phase 3 Acceptance Criteria

| # | Criterion | How to Verify |
|---|---|---|
| 1 | Script builds nodes + edges from notes and exports clean JSON | `secondself graph` produces `data/graph.json` |
| 2 | Interactive force-directed graph renders from that JSON | Open browser, graph appears |
| 3 | Hover reveals note content | Hover over any node |
| 4 | Drag + zoom work | Drag nodes, scroll to zoom |
| 5 | Built from your real notes, not dummy data | Node labels match your actual captures |

**Git checkpoint:** `git add . && git commit -m "Phase 3: The Cartographer — interactive knowledge graph complete"`

---

## Phase 4: The Oracle — "Ask It Anything, Ship It Public"

> **Badge:** 🔮 The Oracle  
> **Duration:** Week 4  
> **Goal:** Natural-language Q&A over your knowledge + deployed to a public URL.  
> **Depends on:** Phase 2 (embeddings) + Phase 3 (graph UI)

### Input
- ChromaDB with all embeddings
- `wiki/` with organized notes
- Graph UI from Phase 3

### Output
- `ask()` function: question → synthesized answer with citations
- Complete web UI with graph + chat
- Deployed to a public URL

---

### Step 4.1 — Implement `ask.py`

**File:** `src/secondself/ask.py`

RAG (Retrieval-Augmented Generation) pipeline:

```python
# What to implement:

@dataclass
class SourceNote:
    id: str
    title: str
    similarity: float
    excerpt: str

@dataclass
class AskResponse:
    answer: str
    sources: list[SourceNote]
    confidence: str              # "high" | "medium" | "low"
    query_embedding_time_ms: float
    retrieval_time_ms: float
    llm_time_ms: float

def ask(question: str, engine: EmbeddingEngine) -> AskResponse:
    """Answer a question using RAG over the knowledge base."""
    # 1. Embed the question (time it)
    # 2. Query ChromaDB for top-K similar notes (time it)
    # 3. Load full content of matched notes from wiki/
    # 4. Build RAG prompt:
    #    - System: "Answer using ONLY the user's knowledge base"
    #    - Context: Retrieved notes with titles
    #    - Question: User's question
    #    - Instructions: Cite sources, be honest about gaps
    # 5. Call Groq API (time it)
    # 6. Parse response
    # 7. Determine confidence based on:
    #    - "high": top result similarity > 0.8
    #    - "medium": top result similarity 0.65–0.8
    #    - "low": top result similarity < 0.65
    # 8. Return AskResponse with answer, sources, timings
```

Add CLI command:

```python
@main.command()
@click.argument("question")
def ask_cmd(question):
    """Ask a question about your knowledge base."""
    # Call ask(question)
    # Print answer with rich formatting
    # Print source citations
    # Print confidence and timings
```

---

### Step 4.2 — Implement `server.py`

**File:** `src/secondself/server.py`

FastAPI server serving both the API and static frontend:

```python
# What to implement:

app = FastAPI(title="SecondSelf", description="Your AI Second Brain")

# Static files
app.mount("/static", StaticFiles(directory="web"), name="static")

@app.get("/")
async def index():
    """Serve the main web page."""
    # Return web/index.html

@app.get("/api/graph")
async def get_graph():
    """Return the knowledge graph JSON."""
    # Read and return data/graph.json

@app.post("/api/ask")
async def ask_endpoint(request: AskRequest):
    """Answer a question using RAG."""
    # Call ask(request.question)
    # Return AskResponse as JSON

@app.post("/api/capture")
async def capture_endpoint(request: CaptureRequest):
    """Capture a new item from the web UI."""
    # Call appropriate capture function
    # Trigger processing (classify, embed, link)
    # Return {id, status}

@app.get("/api/notes")
async def list_notes(category: str = None, tag: str = None):
    """List all notes with optional filters."""

@app.get("/api/notes/{note_id}")
async def get_note(note_id: str):
    """Get a single note's full content."""

@app.get("/api/search")
async def search_notes(q: str, k: int = 5):
    """Semantic search over the knowledge base."""

@app.get("/api/stats")
async def get_stats():
    """Dashboard statistics."""
    # Total notes, by category, recent captures, etc.
```

Add CLI command:

```python
@main.command()
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8000, type=int)
def serve(host, port):
    """Start the SecondSelf web server."""
    # Rebuild graph before starting
    # Run uvicorn
```

---

### Step 4.3 — Build `web/chat.js`

**File:** `web/chat.js`

Chat/ask interface logic:

```javascript
// What to implement:

async function askBrain(question) {
  // 1. Show loading state (pulsing dots animation)
  // 2. POST /api/ask with {question}
  // 3. Parse response
  // 4. Render answer with markdown formatting
  // 5. Render source citations as clickable links
  //    (clicking a source highlights that node in the graph)
  // 6. Show confidence badge and timing info
  // 7. Hide loading state
}

function setupAskBar() {
  // 1. Listen for Enter key or Send button click
  // 2. Get question text from input
  // 3. Call askBrain(question)
  // 4. Clear input
}

function highlightSourceNodes(sourceIds) {
  // 1. Reset all node colors
  // 2. Highlight source nodes with glow effect
  // 3. Focus the graph view on those nodes
}

document.addEventListener('DOMContentLoaded', setupAskBar);
```

---

### Step 4.4 — Polish Web UI

Enhance `web/index.html` and `web/style.css`:

```
Polish checklist:
- [ ] Capture modal (click [Capture +] → modal with note/url/file tabs)
- [ ] Loading states for all async operations
- [ ] Error handling with user-friendly messages
- [ ] Responsive layout (works on mobile)
- [ ] Keyboard shortcuts (/ to focus search, Esc to close panels)
- [ ] Smooth animations for panel transitions
- [ ] Node click highlights connected edges
- [ ] Stats dashboard section (note count, category breakdown)
- [ ] Empty state design (when no notes exist yet)
```

---

### Step 4.5 — Write Tests

**File:** `tests/test_ask.py`

```python
# Tests to implement:
- test_ask_returns_answer()
- test_ask_includes_sources()
- test_ask_cites_relevant_notes()
- test_ask_handles_no_relevant_notes()
- test_ask_response_has_timings()
- test_confidence_levels()
```

---

### Step 4.6 — Deploy to Public URL

Choose deployment platform and configure:

**Option A: Railway (recommended)**
```bash
# 1. Install Railway CLI
npm install -g @railway/cli

# 2. Login
railway login

# 3. Initialize
railway init

# 4. Add environment variables
railway variables set GROQ_API_KEY=your_key_here

# 5. Deploy
railway up
```

**Option B: Render**
```bash
# 1. Create render.yaml in project root:
services:
  - type: web
    name: secondself
    runtime: python
    buildCommand: pip install .
    startCommand: uvicorn secondself.server:app --host 0.0.0.0 --port $PORT

# 2. Push to GitHub
# 3. Connect repo on render.com dashboard
# 4. Add GROQ_API_KEY env var
# 5. Deploy triggers automatically
```

**Deployment files to create:**
- `Procfile`: `web: uvicorn secondself.server:app --host 0.0.0.0 --port $PORT`
- `runtime.txt`: `python-3.11.9` (if needed by platform)

---

### Step 4.7 — Test Real Questions

```bash
# Test locally
secondself ask "What do I know about attention mechanisms?"
secondself ask "Summarize my notes about Python best practices"
secondself ask "What projects am I working on?"
secondself ask "How are transformers related to my ML notes?"
secondself ask "What did I capture about PARA method?"

# Test via web UI
secondself serve
# Open http://localhost:8000
# Use the ask bar to test the same questions
# Verify graph nodes highlight when viewing answers
```

---

### Phase 4 Acceptance Criteria

| # | Criterion | How to Verify |
|---|---|---|
| 1 | `ask()` function returns synthesized answer from notes | `secondself ask "..."` returns relevant answer |
| 2 | Answers cite source notes | Response includes `[Note X]` citations |
| 3 | Web UI shows graph + chat on same page | Open localhost:8000 |
| 4 | Capture from web UI works | Click [Capture +], add a note |
| 5 | Deployed to public URL | Access via Railway/Render URL |
| 6 | Public URL loads graph + accepts questions | Open public URL in incognito |

**Git checkpoint:** `git add . && git commit -m "Phase 4: The Oracle — RAG + deployment complete 🚀"`

---

## Summary: Build Order & Dependencies

```
Week 0 (Setup)
  └── pyproject.toml, config.py, directories, .env
       │
Week 1 (The Archivist)
  └── capture.py → cli.py → tests → 10+ real captures
       │
Week 2 (The Librarian)
  ├── classify.py (needs Groq API key)
  ├── embed.py (downloads model on first run)
  ├── linker.py (needs embed.py)
  └── wiki_writer.py → process CLI → tests → 15+ processed
       │
Week 3 (The Cartographer)
  ├── graph_builder.py (needs wiki/)
  ├── web/index.html + style.css
  └── web/graph.js → graph CLI → tests → interactive graph
       │
Week 4 (The Oracle)
  ├── ask.py (needs embed.py + wiki/)
  ├── server.py (needs everything)
  ├── web/chat.js
  └── deploy → public URL → final tests
```

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| Groq API rate limits | Classification/QA blocked | Batch processing with delays; cache results |
| sentence-transformers model download fails | Embeddings blocked | Pre-download model; fallback to smaller model |
| ChromaDB corruption | Data loss | Regular exports to `data/graph.json`; raw/ is immutable backup |
| URL fetching timeouts | Capture hangs | 10s timeout; capture URL even if fetch fails |
| Wiki filename conflicts | Data overwrite | Append `-2`, `-3` suffix; check before write |
| Large PDFs | Memory/time issues | Limit extracted text to first 50 pages; async processing |
