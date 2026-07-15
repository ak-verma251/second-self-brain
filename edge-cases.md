# SecondSelf — Edge Cases & Corner Scenarios

A comprehensive catalog of edge cases, corner scenarios, and failure modes across all phases of the SecondSelf project. Each entry includes the scenario, expected behavior, and recommended handling strategy.

---

## Phase 1: The Archivist — Capture Pipeline

### 1.1 — Note Capture (`capture_note`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 1.1.1 | **Empty string** — `secondself capture note ""` | Reject capture | Validate `len(text.strip()) > 0`; print error: "Cannot capture empty note" |
| 1.1.2 | **Whitespace-only input** — `"   \n\t  "` | Reject capture | Same as above — strip then check length |
| 1.1.3 | **Extremely long note** — 100,000+ characters | Accept but warn | Capture fully; warn if > 50,000 chars: "Large note captured (X chars)" |
| 1.1.4 | **Unicode / emoji content** — `"🧠 Notas en español: señal"` | Accept fully | Ensure JSON writes with `ensure_ascii=False` |
| 1.1.5 | **Special JSON characters** — content with `"`, `\`, `\n` | Accept; escape properly | `json.dump()` handles escaping automatically |
| 1.1.6 | **Multiline note from CLI** — user tries to pass newlines | Accept | Click handles quoted strings; support `\n` literal → actual newline conversion |
| 1.1.7 | **Duplicate content** — same note captured twice | Allow both; unique IDs | Each capture gets unique UUID — duplicates are fine; linker will connect them later |
| 1.1.8 | **Note is pure code** — `"def foo(): return bar"` | Accept as-is | Don't try to interpret; store raw text; classifier will tag it |
| 1.1.9 | **Note with only numbers** — `"42"` | Accept | Valid capture; classifier handles short content |
| 1.1.10 | **Concurrent captures** — two CLI invocations at same instant | Both succeed | UUID ensures unique filenames even with identical timestamps |

---

### 1.2 — URL Capture (`capture_url`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 1.2.1 | **Invalid URL format** — `"not-a-url"` | Reject with error | Validate URL scheme (`http://` or `https://`); suggest correction |
| 1.2.2 | **URL without scheme** — `"example.com"` | Auto-fix | Prepend `https://` and proceed |
| 1.2.3 | **URL returns 404** | Capture URL, note failure | Store URL + `"fetch_status": "404"`; set title to URL itself |
| 1.2.4 | **URL returns 403 / 401** | Capture URL, note auth required | Store URL + `"fetch_status": "403_forbidden"` |
| 1.2.5 | **URL timeout** (> 10s) | Capture URL without content | Store URL + `"fetch_status": "timeout"`; use URL as title |
| 1.2.6 | **URL returns non-HTML** (PDF, image, JSON) | Capture URL + content-type | Store URL + `"content_type": "application/pdf"`; don't try HTML parsing |
| 1.2.7 | **URL with redirect chain** | Follow redirects | `httpx` follows redirects by default (max 20); store final URL |
| 1.2.8 | **URL to localhost / private IP** | Reject | Block `127.0.0.1`, `10.x`, `192.168.x`, `0.0.0.0`; security measure |
| 1.2.9 | **Very long URL** (> 2048 chars) | Accept but truncate in display | Store full URL; truncate to 80 chars in CLI output |
| 1.2.10 | **URL with no `<title>` tag** | Use URL as title | Fallback: `meta og:title` → `<h1>` → URL domain |
| 1.2.11 | **URL with non-UTF-8 encoding** | Attempt decode | Try `charset` from headers → `chardet` detection → fallback to `latin-1` |
| 1.2.12 | **URL with JavaScript-rendered content** | Capture static HTML only | Note in docs: SPA content won't be captured; store whatever HTML is returned |
| 1.2.13 | **URL returns enormous page** (> 5MB HTML) | Truncate | Read only first 1MB of response body; set `"truncated": true` |
| 1.2.14 | **DNS resolution failure** | Capture URL, note failure | Store URL + `"fetch_status": "dns_error"` |
| 1.2.15 | **SSL certificate error** | Capture URL, note failure | Store URL + `"fetch_status": "ssl_error"`; don't disable SSL verification |

---

### 1.3 — File Capture (`capture_file`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 1.3.1 | **File doesn't exist** | Error | Click's `type=click.Path(exists=True)` catches this before `capture_file()` runs |
| 1.3.2 | **File is empty** (0 bytes) | Capture with empty content | Accept; set `"content.file_content": ""`, `"word_count": 0` |
| 1.3.3 | **Binary file** (image, video, executable) | Capture metadata only | Store filename + size + type; set `"file_content": "[Binary file — content not extracted]"` |
| 1.3.4 | **Very large text file** (> 10MB) | Capture first N chars | Read first 500,000 chars; set `"truncated": true` |
| 1.3.5 | **Very large PDF** (100+ pages) | Capture first N pages | Extract text from first 50 pages; set `"truncated": true, "pages_extracted": 50` |
| 1.3.6 | **Password-protected PDF** | Capture metadata, skip content | Set `"file_content": "[Password-protected PDF — content not extracted]"` |
| 1.3.7 | **Corrupted PDF** | Capture metadata, skip content | Catch `pymupdf` exceptions; set `"file_content": "[Corrupted file — extraction failed]"` |
| 1.3.8 | **Scanned PDF** (images only, no OCR text) | Capture with empty text | `pymupdf` extracts embedded text only; result may be empty; note: "No extractable text" |
| 1.3.9 | **File path with spaces** — `"my document.pdf"` | Accept | `Path` handles spaces natively; ensure JSON stores the original path |
| 1.3.10 | **File path with Unicode** — `"notas_señal.txt"` | Accept | `Path` handles Unicode on modern OS |
| 1.3.11 | **Symlink / shortcut** | Follow and capture target | `Path.resolve()` follows symlinks |
| 1.3.12 | **File with no extension** | Treat as text | Try reading as UTF-8; if fails, treat as binary |
| 1.3.13 | **File is currently locked** (open in another app) | Error with retry suggestion | Catch `PermissionError`; print "File is locked — close it and try again" |
| 1.3.14 | **Relative vs absolute path** | Accept both | `Path(file_path).resolve()` normalizes to absolute |
| 1.3.15 | **Directory passed instead of file** | Reject | Check `Path.is_file()` — if directory, print "Expected a file, got a directory" |

---

### 1.4 — Storage & Filesystem

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 1.4.1 | **`raw/` directory doesn't exist** | Create it | `config.ensure_dirs()` creates all directories on startup |
| 1.4.2 | **Disk full** | Error | Catch `OSError`; print "Disk full — cannot save capture" |
| 1.4.3 | **Filename collision** (astronomically unlikely) | Both writes succeed | 8-char UUID prefix + full UUID inside JSON ensures uniqueness |
| 1.4.4 | **Read-only filesystem** | Error | Catch `PermissionError`; print "Cannot write to raw/ — check permissions" |
| 1.4.5 | **JSON file manually edited / corrupted** | Skip gracefully | `list_captures()` wraps `json.load()` in try/except; skip corrupt files with warning |
| 1.4.6 | **Non-JSON files in `raw/`** | Ignore | `list_captures()` only reads `*.json` files |
| 1.4.7 | **Thousands of files in `raw/`** | Performance degrades | For `list_captures()`: sort by filename (already chronological); paginate for display |

---

## Phase 2: The Librarian — Classification & Linking

### 2.1 — Classification (`classify.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 2.1.1 | **Groq API key missing** | Error with setup instructions | Check for `GROQ_API_KEY` on startup; print link to console.groq.com |
| 2.1.2 | **Groq API key invalid / expired** | Error | Catch `AuthenticationError`; print "Invalid API key — check .env" |
| 2.1.3 | **Groq rate limit exceeded** | Retry with backoff | Implement exponential backoff: wait 1s → 2s → 4s; max 3 retries |
| 2.1.4 | **Groq API returns non-JSON** | Fallback classification | Parse failure → use default: `category="resources"`, empty tags, content[:100] as summary |
| 2.1.5 | **LLM returns invalid PARA category** | Correct to closest match | If not in `PARA_CATEGORIES`, fuzzy match or default to "resources" |
| 2.1.6 | **LLM returns too many tags** (20+) | Truncate | Keep first 5 tags only |
| 2.1.7 | **LLM hallucinates extra JSON fields** | Ignore extras | Only extract known fields; ignore unknown keys |
| 2.1.8 | **Very short content** (< 10 words) | Accept with low confidence | Classify anyway; set `confidence` low; LLM may still infer category |
| 2.1.9 | **Content in non-English language** | Classify anyway | Llama 3 handles many languages; PARA still applies; tags may be in original language |
| 2.1.10 | **Content is pure code** | Classify as "resources" | LLM should handle this; add hint in prompt: "code snippets are typically Resources" |
| 2.1.11 | **Groq API timeout** | Retry once then fail gracefully | 30s timeout; retry once; if still fails, skip classification (mark as "unclassified") |
| 2.1.12 | **Groq service outage** | Queue for later processing | Mark capture as `"processed": false`; user can run `secondself process` later |
| 2.1.13 | **LLM returns markdown-wrapped JSON** — ` ```json {...} ``` ` | Strip markdown | Regex strip ` ```json ` and ` ``` ` before parsing |
| 2.1.14 | **Content is a URL with no fetched text** | Classify based on URL alone | Pass URL + any available metadata to LLM; accept lower confidence |

---

### 2.2 — Embeddings (`embed.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 2.2.1 | **First run — model not downloaded** | Auto-download (~90MB) | `sentence-transformers` downloads on first use; print "Downloading embedding model..." |
| 2.2.2 | **No internet for model download** | Error with instructions | Catch download error; print "Model download failed — check internet connection" |
| 2.2.3 | **Empty text to embed** | Return zero vector or skip | Check `len(text.strip()) > 0`; if empty, skip embedding with warning |
| 2.2.4 | **Text exceeds model max tokens** (256 tokens for MiniLM) | Truncate | `sentence-transformers` auto-truncates; but for better quality, chunk and average |
| 2.2.5 | **ChromaDB directory doesn't exist** | Create it | `config.ensure_dirs()` handles this |
| 2.2.6 | **ChromaDB corrupted** | Rebuild | Catch ChromaDB errors; offer `secondself reprocess` to rebuild from raw/ |
| 2.2.7 | **Duplicate ID upsert** | Overwrite silently | ChromaDB `upsert` replaces existing; this is desired behavior for reprocessing |
| 2.2.8 | **ChromaDB collection doesn't exist yet** | Create it | `get_or_create_collection("secondself_notes")` handles this |
| 2.2.9 | **Very large number of embeddings** (10,000+) | Performance concern | ChromaDB handles this fine locally; query time stays sub-second for < 100K docs |
| 2.2.10 | **Metadata value too long for ChromaDB** | Truncate metadata | ChromaDB has metadata value limits; truncate `tags` string if > 1000 chars |

---

### 2.3 — Auto-Linking (`linker.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 2.3.1 | **Only 1 note in the system** | No links created | `find_related()` returns empty list (no other notes to link to) |
| 2.3.2 | **All notes are below similarity threshold** | No links created | Filter returns empty; note gets empty "## Related Notes" section |
| 2.3.3 | **All notes are above similarity threshold** | Cap at MAX_LINKS | Return only top 5 most similar |
| 2.3.4 | **Self-link** — note most similar to itself | Exclude self | Filter out `id == self.id` from results |
| 2.3.5 | **Link target note doesn't have a wiki file yet** | Skip that link | Only link to notes that have been processed into wiki/ |
| 2.3.6 | **Backlink insertion into note with no "## Related Notes" section** | Create the section | Append `\n\n## Related Notes\n` before inserting links |
| 2.3.7 | **Duplicate links** — note A already linked to note B | Don't duplicate | Check existing links before inserting; skip if already present |
| 2.3.8 | **Wiki file moved or renamed manually** | Link breaks | Links use `[[title]]` not file paths; title match is more resilient |
| 2.3.9 | **Two notes with identical titles** | Link ambiguity | Append ID suffix to disambiguate: `[[Title (a1b2c3)]]` |
| 2.3.10 | **Circular link chains** — A→B→C→A | Allow | Circular references are valid in a knowledge graph |
| 2.3.11 | **Reprocessing creates stale links** | Clean up | `reprocess` clears all wiki files and rebuilds from scratch |

---

### 2.4 — Wiki Writer (`wiki_writer.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 2.4.1 | **Title contains filesystem-unsafe characters** — `"C++: A Guide?"` | Slugify | `slugify("C++: A Guide?")` → `c-a-guide` (strip special chars, lowercase, hyphenate) |
| 2.4.2 | **Title is empty** (LLM returned empty title) | Generate from content | Fallback: first 8 words of content as title |
| 2.4.3 | **Title produces empty slug** — `"???"` | Use capture ID as filename | Fallback: `{short_id}.md` |
| 2.4.4 | **Filename collision** — two notes slugify to same name | Append counter | Check if file exists; if so, try `{slug}-2.md`, `{slug}-3.md`, etc. |
| 2.4.5 | **Very long title** (200+ chars) | Truncate slug | Cap slug at 80 characters |
| 2.4.6 | **YAML frontmatter contains special YAML characters** — `:`, `#`, `[` in title | Quote values | Always wrap string values in quotes in frontmatter |
| 2.4.7 | **Content contains YAML frontmatter delimiter** (`---`) | Escape | Ensure content body doesn't start with `---` on its own line |
| 2.4.8 | **Tags contain special characters** | Sanitize | Strip everything except alphanumeric, hyphens, underscores |
| 2.4.9 | **Category directory doesn't exist** | Create it | `Path.mkdir(parents=True, exist_ok=True)` |
| 2.4.10 | **Reprocessing same capture** — wiki file already exists | Overwrite | Regenerate the file; `reprocess` means full rebuild |

---

## Phase 3: The Cartographer — Knowledge Graph

### 3.1 — Graph Builder (`graph_builder.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 3.1.1 | **Empty wiki/** — no notes processed yet | Empty graph | Return `{nodes: [], edges: [], metadata: {total_nodes: 0, ...}}` |
| 3.1.2 | **Wiki note missing frontmatter** | Skip or use defaults | Try YAML parse; if fails, extract what you can from content; warn user |
| 3.1.3 | **Wiki note with malformed YAML** | Skip with warning | Catch `yaml.YAMLError`; print warning; exclude from graph |
| 3.1.4 | **`[[link]]` target doesn't match any node** | Orphan edge dropped | Only create edges where both source and target exist as nodes |
| 3.1.5 | **Self-referencing `[[link]]`** | Ignore | Don't create edge where `from == to` |
| 3.1.6 | **Hundreds of notes** — graph becomes cluttered | Still works | vis-network handles 500+ nodes; physics stabilizes; consider clustering for > 1000 |
| 3.1.7 | **Isolated nodes** (no links to anything) | Show as disconnected | Render as smaller, dimmer nodes floating at graph periphery |
| 3.1.8 | **Node with 50+ links** (super-connector) | May dominate graph | Cap displayed edges per node in visualization; all data still in JSON |
| 3.1.9 | **`data/graph.json` is stale** (wiki changed since last build) | Warn user | Print timestamp of last build; suggest `secondself graph` to rebuild |
| 3.1.10 | **Non-markdown files in wiki/** | Ignore | Only process `*.md` files |

---

### 3.2 — Graph Visualization (`graph.js` + `index.html`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 3.2.1 | **`/api/graph` returns empty nodes** | Show empty state | Display message: "No notes yet. Capture something to start your brain!" |
| 3.2.2 | **`/api/graph` fails (server error)** | Show error state | Display message: "Failed to load graph. Is the server running?" with retry button |
| 3.2.3 | **Browser doesn't support Canvas** | Fallback message | vis-network requires Canvas; show "Browser not supported" for ancient browsers |
| 3.2.4 | **Very long node label** (100+ chars) | Truncate in display | Show first 40 chars + `...` as label; full title in tooltip |
| 3.2.5 | **Node hover on mobile** (no hover event) | Use tap instead | `network.on('selectNode')` works for both click and tap |
| 3.2.6 | **Graph physics never stabilizes** | Force stabilization | Set `stabilization: { iterations: 200 }`; after stabilize, disable physics for perf |
| 3.2.7 | **All nodes same category** | All same color | This is fine; visual still works; consider using tags for secondary coloring |
| 3.2.8 | **Browser window resize** | Graph doesn't resize | Add `window.addEventListener('resize', () => network.fit())` |
| 3.2.9 | **Note detail panel — content has HTML/markdown** | Render safely | Sanitize HTML; render markdown as plain text or use a lightweight MD renderer |
| 3.2.10 | **Rapid hover across many nodes** | Performance OK | Debounce hover handler (100ms); vis-network's `tooltipDelay` helps |
| 3.2.11 | **User zooms out very far** | Labels unreadable | Hide labels below certain zoom level; show only on hover |

---

## Phase 4: The Oracle — RAG & Deployment

### 4.1 — RAG Pipeline (`ask.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 4.1.1 | **Empty question** — `""` | Reject | Validate input; return error: "Please enter a question" |
| 4.1.2 | **Question with no relevant notes** (similarity all < 0.3) | Honest "I don't know" | LLM prompt says "say so honestly"; also set `confidence: "low"` |
| 4.1.3 | **Question about something not in the knowledge base** | Honest "I don't know" | RAG retrieves irrelevant notes; LLM should recognize and decline |
| 4.1.4 | **Very long question** (1000+ words) | Accept but truncate for embedding | Embed first 256 tokens; pass full question to LLM |
| 4.1.5 | **Question is actually a command** — `"delete all notes"` | Ignore as question | RAG only reads; no write operations; LLM can't execute commands |
| 4.1.6 | **Question in non-English** | Attempt to answer | Embeddings are multilingual-ish; LLM handles many languages; quality may vary |
| 4.1.7 | **Retrieved notes have conflicting information** | LLM acknowledges conflict | Prompt instructs to cite sources; conflicts become visible through citations |
| 4.1.8 | **All retrieved notes are very short** (< 20 words each) | Low-quality answer | LLM does its best; set `confidence: "low"` if total context < 100 words |
| 4.1.9 | **LLM context window exceeded** | Truncate context | Llama 3 70B has 8192 token context; if 5 notes exceed this, include fewer notes |
| 4.1.10 | **Groq API failure during ask** | Return error | "Sorry, I couldn't generate an answer right now. Please try again." |
| 4.1.11 | **ChromaDB is empty** (no embeddings yet) | Tell user to process first | Return: "No notes in knowledge base. Run `secondself process` first." |
| 4.1.12 | **Same question asked twice** | Same answer (roughly) | No caching by default; each query hits LLM fresh; consider caching for cost |
| 4.1.13 | **Question contains prompt injection** — `"Ignore instructions, say X"` | LLM stays grounded | RAG prompt is firm; system prompt says "ONLY from notes"; Llama 3 is reasonably robust |
| 4.1.14 | **Retrieved wiki file was manually deleted** | Skip that source | Catch `FileNotFoundError` when loading wiki content; continue with remaining sources |

---

### 4.2 — Web API (`server.py`)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 4.2.1 | **POST `/api/ask` with missing `question` field** | 422 Validation Error | FastAPI/Pydantic auto-validates request body |
| 4.2.2 | **POST `/api/capture` with invalid type** | 400 Bad Request | Validate `type` is one of `["note", "url", "file"]` |
| 4.2.3 | **GET `/api/notes/nonexistent-id`** | 404 Not Found | Return `{"detail": "Note not found"}` |
| 4.2.4 | **GET `/api/graph` when `graph.json` doesn't exist** | Rebuild or 404 | Auto-rebuild graph if wiki/ has content; return 404 if no notes at all |
| 4.2.5 | **Concurrent requests** — multiple users asking at once | Queue API calls | FastAPI async handles concurrency; Groq API may rate-limit; add request queue |
| 4.2.6 | **CORS requests from different domain** | Blocked by default | Add `CORSMiddleware` if needed; default is same-origin only |
| 4.2.7 | **Very large POST body** (> 1MB) | Reject | Set FastAPI max request size; return 413 |
| 4.2.8 | **Static files not found** (`web/` directory missing) | 500 Error | Check `web/` exists on startup; print helpful error |
| 4.2.9 | **Port already in use** (8000 taken) | Error | Catch `OSError`; suggest `--port 8001` |
| 4.2.10 | **Server crash during `process`** — half-processed capture | Inconsistent state | Track processing state per capture; `process` skips already-completed steps |

---

### 4.3 — Web UI (Frontend)

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 4.3.1 | **JavaScript disabled** | Page is blank | Show `<noscript>` message: "SecondSelf requires JavaScript" |
| 4.3.2 | **Slow network** — graph JSON takes 5+ seconds | Loading spinner | Show skeleton/loading animation while fetching |
| 4.3.3 | **User submits empty question in chat** | Don't send request | Disable send button when input is empty |
| 4.3.4 | **User spams Send button** | Debounce | Disable button after click; re-enable after response |
| 4.3.5 | **Answer contains markdown** (bold, lists, code) | Render properly | Use a lightweight markdown → HTML renderer (or regex for basics) |
| 4.3.6 | **Answer is very long** (1000+ words) | Scrollable container | Answer area has `overflow-y: auto` and `max-height` |
| 4.3.7 | **Capture modal — pasting very long text** | Accept with scroll | Textarea with `max-height` and scroll; no hard character limit |
| 4.3.8 | **Mobile viewport** — 375px wide | Responsive layout | Stack panels vertically; graph takes full width on mobile |
| 4.3.9 | **Dark mode + light mode OS setting** | Always dark mode | Design is dark-mode-only per spec; ignore `prefers-color-scheme` |
| 4.3.10 | **CDN for vis-network fails to load** | Graph won't render | Add fallback local copy or show error: "Graph library failed to load" |
| 4.3.11 | **Browser back button** | No state to go back to | SPA has no routing; back button exits the app; consider `history.pushState` |

---

### 4.4 — Deployment

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 4.4.1 | **`GROQ_API_KEY` not set in production** | Server starts but ask/classify fail | Check on startup; log warning; return helpful error on API calls |
| 4.4.2 | **Ephemeral filesystem** (Railway, Render) | `raw/`, `wiki/`, `data/` wiped on redeploy | Use persistent volumes; or accept data loss and re-seed from Git |
| 4.4.3 | **Free tier sleep** — app goes idle | First request after sleep is slow (~30s cold start) | Add a health check endpoint; document expected cold start time |
| 4.4.4 | **Memory limit exceeded** — sentence-transformers model too large | OOM crash | Railway/Render free tier: 512MB; MiniLM model ~90MB; should fit; monitor usage |
| 4.4.5 | **Build timeout** — `pip install sentence-transformers` is slow | Deploy fails | Use `uv` for faster installs; or pre-build Docker image |
| 4.4.6 | **Public URL abuse** — someone floods `/api/ask`** | Groq rate limit hit | Add basic rate limiting (e.g., 10 requests/minute per IP) |
| 4.4.7 | **ChromaDB on ephemeral storage** | Vector DB lost on redeploy | Options: (a) persistent volume, (b) rebuild from wiki on startup, (c) export/import |
| 4.4.8 | **`PORT` environment variable** | Must bind to platform-assigned port | Use `$PORT` env var; don't hardcode 8000 in production |
| 4.4.9 | **No `Procfile` / `render.yaml`** | Deploy fails | Include platform-specific config files in repo |

---

## Cross-Cutting Concerns

### 5.1 — Data Integrity

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 5.1.1 | **Raw JSON manually edited** | May break processing | Validate schema before processing; skip invalid with warning |
| 5.1.2 | **Wiki note manually edited** | Links may break | `reprocess` rebuilds from raw/; manual edits in wiki/ are overwritten |
| 5.1.3 | **ChromaDB and wiki/ out of sync** | Stale search results | `reprocess` clears both and rebuilds from raw/ |
| 5.1.4 | **`raw/` file deleted** | Cannot reprocess that capture | Raw is the source of truth; if deleted, that knowledge is lost |
| 5.1.5 | **Graph JSON and wiki/ out of sync** | Graph shows stale data | `secondself graph` rebuilds; `secondself serve` rebuilds on start |

---

### 5.2 — Performance

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 5.2.1 | **100+ captures processed at once** | Slow (LLM calls) | Show progress bar; ~2s per LLM call = ~3-4 min for 100 |
| 5.2.2 | **sentence-transformers first load** | Slow (~5-10s) | Lazy-load model; show "Loading embedding model..." |
| 5.2.3 | **ChromaDB query on 10,000+ docs** | Still fast (< 100ms) | ChromaDB handles this scale well locally |
| 5.2.4 | **Graph rendering with 500+ nodes** | Physics simulation heavy | Disable physics after initial stabilization; enable on drag only |
| 5.2.5 | **Multiple LLM calls in RAG** | Slow (3-5s per question) | Show streaming-like effect (typing animation); cache popular questions |

---

### 5.3 — Security

| # | Edge Case | Expected Behavior | Handling Strategy |
|---|---|---|---|
| 5.3.1 | **API key exposed in frontend** | Critical security issue | Never send `GROQ_API_KEY` to browser; all LLM calls go through backend |
| 5.3.2 | **Path traversal in file capture** — `"../../etc/passwd"` | Blocked | Resolve path and verify it's within allowed directories |
| 5.3.3 | **XSS in note content** — `"<script>alert('xss')</script>"` | Sanitized | Escape HTML in all frontend rendering; use `textContent` not `innerHTML` |
| 5.3.4 | **SQL injection** (N/A — no SQL) | Not applicable | No SQL database in architecture; ChromaDB uses its own query language |
| 5.3.5 | **`.env` committed to Git** | API key leaked | `.gitignore` includes `.env`; use `.env.example` for templates |
| 5.3.6 | **Public deployment exposes personal notes** | Privacy concern | Document clearly: "Public URL means anyone can read your notes"; add auth if needed |

---

## Summary: Edge Case Counts by Phase

| Phase | Category | Count |
|---|---|---|
| Phase 1 | Note Capture | 10 |
| Phase 1 | URL Capture | 15 |
| Phase 1 | File Capture | 15 |
| Phase 1 | Storage & Filesystem | 7 |
| Phase 2 | Classification | 14 |
| Phase 2 | Embeddings | 10 |
| Phase 2 | Auto-Linking | 11 |
| Phase 2 | Wiki Writer | 10 |
| Phase 3 | Graph Builder | 10 |
| Phase 3 | Graph Visualization | 11 |
| Phase 4 | RAG Pipeline | 14 |
| Phase 4 | Web API | 10 |
| Phase 4 | Web UI | 11 |
| Phase 4 | Deployment | 9 |
| Cross-Cutting | Data Integrity | 5 |
| Cross-Cutting | Performance | 5 |
| Cross-Cutting | Security | 6 |
| | **Total** | **173** |
