# 🧠 SecondSelf — Your Personal AI Second Brain

An AI-powered personal knowledge management system that captures, classifies, links, visualizes, and answers questions from your own knowledge.

## Features

- **📥 Capture** — One command captures notes, URLs, and files into an immutable store
- **🏷️ Classify** — AI auto-categorizes using the PARA method (Projects, Areas, Resources, Archives)
- **🔗 Auto-Link** — Semantic embeddings discover and create connections between related notes
- **🗺️ Visualize** — Interactive force-directed knowledge graph in the browser
- **💬 Ask** — Natural-language Q&A over your entire knowledge base using RAG

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Groq API key](https://console.groq.com) (free tier)

### Setup

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd secondself

# 2. Copy environment template and add your API key
cp .env.example .env
# Edit .env and add your GROQ_API_KEY

# 3. Install dependencies
uv sync

# 4. Verify installation
python -c "from secondself.config import RAW_DIR; print(RAW_DIR)"
```

### Usage

```bash
# Capture knowledge
secondself capture note "Attention is all you need — transformers replace RNNs"
secondself capture url "https://arxiv.org/abs/1706.03762"
secondself capture file "./document.pdf"

# View captures
secondself list
secondself show <id>

# Process & organize (AI-powered)
secondself process

# Search your brain
secondself search "machine learning"

# Ask questions
secondself ask "What do I know about transformers?"

# Launch web UI
secondself serve
```

## Architecture

See [architecture.md](architecture.md) for the full system design.

## Project Structure

```
secondself/
├── raw/               # Immutable capture store (JSON)
├── wiki/              # Organized knowledge (PARA Markdown)
│   ├── projects/
│   ├── areas/
│   ├── resources/
│   └── archives/
├── data/              # ChromaDB vectors + graph JSON
├── src/secondself/    # Python source code
├── web/               # Static frontend (HTML/CSS/JS)
└── tests/             # Test suite
```

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| CLI | Click |
| LLM | Groq (Llama 3 70B) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector Store | ChromaDB |
| Web Backend | FastAPI |
| Graph Viz | vis-network.js |
| Frontend | Vanilla HTML/CSS/JS |

## License

MIT
