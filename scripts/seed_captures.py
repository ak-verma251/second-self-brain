"""Script to capture 10+ real items for Phase 1 verification."""

from secondself.capture import capture_note, capture_url, capture_file
import time

items = [
    # Notes about AI/ML concepts
    ("note", "PARA method: Projects, Areas, Resources, Archives — a system by Tiago Forte for organizing digital knowledge into four actionable categories"),
    ("note", "RAG (Retrieval-Augmented Generation) combines vector search with LLM generation to answer questions grounded in a knowledge base, reducing hallucinations"),
    ("note", "Embeddings convert text into dense vectors in high-dimensional space where semantic similarity maps to geometric proximity. all-MiniLM-L6-v2 produces 384-dim vectors"),
    ("note", "ChromaDB is an embedded vector database for Python — zero infrastructure, persistent storage, and native cosine similarity search"),
    ("note", "The Feynman Technique: 1) Choose a concept, 2) Teach it to a child, 3) Identify gaps, 4) Review and simplify. Best method for deep understanding"),
    ("note", "Zettelkasten method — atomic notes connected by links create emergent knowledge structures. Every note should be self-contained and link to related ideas"),
    ("note", "Python type hints with dataclasses provide clean data modeling: @dataclass for structure, type annotations for documentation, and runtime validation with Pydantic"),
    ("note", "FastAPI serves both REST APIs and static files — perfect for single-binary web apps. Auto-generates OpenAPI docs and supports async natively"),
    ("note", "Knowledge graphs represent information as nodes (entities) and edges (relationships). Force-directed layouts reveal cluster structure and central concepts"),

    # URLs
    ("url", "https://arxiv.org/abs/1706.03762"),
    ("url", "https://docs.trychroma.com/docs/overview/introduction"),

    # File (capture the architecture doc itself)
    ("file", "architecture.md"),
]

for item_type, content in items:
    try:
        if item_type == "note":
            capture_note(content)
        elif item_type == "url":
            capture_url(content)
        elif item_type == "file":
            capture_file(content)
        time.sleep(0.1)  # Small delay for unique timestamps
    except Exception as e:
        print(f"Error capturing {item_type}: {e}")

print("\n--- Done! ---")
