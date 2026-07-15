# Project: SecondSelf - Your Personal AI Second Brain

## Problem Statement
Every notes app fails the same way: you capture hundreds of notes, bookmarks, PDFs, and ideas and then you never find them again. Information goes in, but nothing comes back out. Notes sit in folders nobody re-reads. Bookmarks pile up unread. Knowledge doesn't compound.

**Goal:** Build an end-to-end system where you can capture anything (a note, a link, a file), have AI automatically classify and file it, auto-link it to related knowledge, render it as a live interactive graph you can explore, and most importantly ask it any question in plain English and get an answer synthesized from your own accumulated knowledge. Then deploy it to a public URL anyone can open.

Not a notes app. Not a chatbot. A brain that organizes itself and answers for you.

---

## Final System (what you're building over 4 weeks)

* Capture any note/link/file
* ↓
* AI classifies & files it (PARA method)
* ↓
* AI auto-links it to related notes (embeddings)
* ↓
* Everything renders as a live, interactive, hoverable graph
* ↓
* Ask it anything in plain English — answer pulled from YOUR notes
* ↓
* Deployed on a public URL anyone can open

---

## Week-by-Week Problem Statements
Each week is a self-contained problem. Build it, test it on real data (your own notes, not test data), and each week's output becomes the next week's input.

### Week 1: The Archivist - "Capture Everything, Lose Nothing"
**Problem:** You have no single place to put things. Ideas, links, and notes scatter across apps, browser tabs, and your memory. Build the foundation: one command that captures anything into one place.

**Build:**
1. Set up the project structure from scratch: `raw/` (where every raw capture lands) and `wiki/` (used later, organized, linked notes).
2. Write a Python capture script that takes any note, link, or file and saves it into `raw/` with a timestamp, a unique ID, and the raw content.
3. Test it on 10+ real pieces of your own scattered information.

**Deliverable ("Ship the Capture Pipeline") & Acceptance Criteria:**
* **Badge:** The Archivist
* A working capture script where one command saves anything to `raw/` with timestamp + unique ID.
* Your `raw/` folder populated with 10+ real captured items (not test data).
* [ ] `raw/` and `wiki/` folder structure exists.
* [ ] One command captures a note, a link, AND a file.
* [ ] Every capture has a timestamp + unique ID.
* [ ] 10+ real items captured.

### Week 2: The Librarian - "Teach AI to Organize For You"
**Problem:** A pile of raw captures is still a mess. Manual tagging never happens. Make the AI do the filing and make it notice when two notes are about the same thing and link them automatically.

**Build - Auto-Classify (The Sorting Hat):** Write a function that sends any raw capture to a free LLM (Groq / Llama 3) and gets back a category (using the PARA framework: Projects, Areas, Resources, Archives), tags, and a one-line summary. Run it across last week's real captures and watch them organize themselves.

**Build - Auto-Link Related Notes (Connect the Dots):** Compute embeddings for each note (sentence-transformers, local + free). Compare each new capture against existing notes in `wiki/`. When content is related (similarity above a threshold), auto-insert a link between them. No manual tagging — the system notices relationships on its own.

**Deliverable ("Ship the Self-Organizing Wiki") & Acceptance Criteria:**
* **Badge:** The Librarian
* A pipeline that auto-classifies raw captures with PARA and auto-links related notes.
* Run on 15+ real items to create an organized `wiki/` folder with linked notes.
* [ ] Any raw capture -> category + tags + summary automatically.
* [ ] PARA categorization working.
* [ ] Embeddings computed per note.
* [ ] Related notes auto-linked (no manual tagging).
* [ ] Runs on 15+ real items -> organized `wiki/`.

### Week 3: The Cartographer - "Visualize the Brain"
**Problem:** Your knowledge is now organized and linked, but you can't see it. Turn the wiki into something you can actually look at, explore, and watch think.

**Build - Graph Data Model (Give It a Shape):** Write a script that reads every note and its links. Build a nodes-and-edges representation in memory: every note is a node, and every relationship/link is an edge. Export it as clean JSON.

**Build - Interactive Graph (The Brain Comes Alive):** Use a JS graph library (vis-network or Cytoscape.js) to render notes as nodes (that pulse / are visually alive), links as edges, hover popups that reveal each note's content, and drag-to-explore and zoom functionality. This creates a force-directed graph of your own knowledge.

**Deliverable ("Ship the Living Brain") & Acceptance Criteria:**
* **Badge:** The Cartographer
* Your wiki converted to a graph and rendered as an interactive visual brain (hover, drag, zoom), built from your real notes.
* [ ] Script builds nodes + edges from notes and exports clean JSON.
* [ ] Interactive force-directed graph renders from that JSON.
* [ ] Hover reveals note content.
* [ ] Drag + zoom work.
* [ ] Built from your real notes, not dummy data.

### Week 4: The Oracle - "Ask It Anything, Ship It Public"
**Problem:** A visual brain is beautiful, but the real payoff is answers. Wire up natural-language search over everything you know, then package the whole thing into one deployable product.

**Build - Ask Your Brain (Natural Language Search):** Build a single `ask()` function that combines the embeddings (to find relevant notes to a question), the wiki (the source content), and an LLM (to synthesize an answer from retrieved notes). This is retrieval-augmented Q&A over your own knowledge. Test against real questions about your own captured notes.

**Build - UI, Deployment, Public URL (Give It a