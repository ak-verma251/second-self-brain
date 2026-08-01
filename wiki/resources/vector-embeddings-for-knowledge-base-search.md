---
id: bb200002-2024-4b70-9de9-second-self02
title: "Vector Embeddings for Knowledge Base Search"
category: resources
tags: ["vector embeddings", "semantic search", "sentence-transformers"]
created: 2026-07-24T08:10:00.000000+05:30
source: cli
confidence: 0.98
---
# Vector Embeddings for Knowledge Base Search


> Vector embeddings for semantic search in a personal knowledge base


## Content


Vector embeddings are dense numerical representations of text where semantic similarity maps to
geometric proximity. The sentence-transformers library (all-MiniLM-L6-v2) produces 384-dimensional
unit-norm vectors. ChromaDB stores these vectors and supports fast approximate nearest-neighbour
search using cosine distance, making it ideal for semantic search and auto-linking in a personal
knowledge base.


## Related Notes
- [[Retrieval-Augmented Generation (RAG) Overview]]
