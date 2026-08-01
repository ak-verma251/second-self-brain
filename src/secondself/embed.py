"""
SecondSelf — Embedding Engine (Step 2.2)

Handles:
  - Text → 384-dim vector via sentence-transformers (all-MiniLM-L6-v2)
  - Persistent storage in ChromaDB (data/chroma/)
  - Semantic similarity queries by text or by existing capture ID
"""

from __future__ import annotations

import json
import os
from typing import Any

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from secondself.config import (
    CHROMA_DIR,
    EMBEDDING_DIM,
    EMBEDDING_MODEL,
    TOP_K_RETRIEVAL,
)

# ChromaDB collection used across the whole application
COLLECTION_NAME = "secondself_notes"


class EmbeddingEngine:
    """Manages text embeddings and their ChromaDB storage.

    Usage::

        engine = EmbeddingEngine()
        engine.store("abc123", "Some note text", {"category": "resources"})
        results = engine.query_similar("machine learning", k=5)
    """

    def __init__(self) -> None:
        # Load the sentence-transformers model.
        # Try offline first (uses local cache) to avoid HuggingFace network
        # calls that fail behind firewalls. Falls back to online download only
        # when the model has never been cached before.
        try:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            self._model: SentenceTransformer = SentenceTransformer(
                EMBEDDING_MODEL, local_files_only=True
            )
        except Exception:
            # Model not in cache yet — allow one-time online download
            os.environ.pop("HF_HUB_OFFLINE", None)
            self._model = SentenceTransformer(EMBEDDING_MODEL)

        # Persistent ChromaDB client — stores data in data/chroma/
        self._client = chromadb.PersistentClient(
            path=str(CHROMA_DIR),
            settings=Settings(anonymized_telemetry=False),
        )

        # Get or create the notes collection.
        # We supply our own embedding function so ChromaDB never tries to
        # re-embed on its own; all vectors come from _model.
        self.collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # cosine distance for similarity
        )

    # ─── Core embedding ──────────────────────────────────────────────────────

    def embed_text(self, text: str) -> list[float]:
        """Return a 384-dimensional embedding vector for *text*.

        Args:
            text: The plain-text string to embed.

        Returns:
            A list of *EMBEDDING_DIM* floats.
        """
        vector: list[float] = self._model.encode(
            text,
            normalize_embeddings=True,  # unit-norm → cosine sim == dot product
            show_progress_bar=False,
        ).tolist()
        assert len(vector) == EMBEDDING_DIM, (
            f"Expected {EMBEDDING_DIM}-dim vector, got {len(vector)}"
        )
        return vector

    # ─── Storage ─────────────────────────────────────────────────────────────

    def store(self, capture_id: str, text: str, metadata: dict[str, Any]) -> None:
        """Embed *text* and upsert it into ChromaDB.

        Args:
            capture_id: Unique identifier for this capture (used as the
                        ChromaDB document ID, so calling this twice with the
                        same ID is safe — it will just overwrite).
            text:       The plain-text content to embed and index.
            metadata:   Arbitrary key/value pairs stored alongside the vector.
                        ``tags`` values should be JSON-serialised strings
                        (ChromaDB only accepts str/int/float/bool values).

        Example metadata dict::

            {
                "category": "resources",
                "tags": '["machine-learning", "nlp"]',   # JSON string
                "title": "Attention is All You Need",
                "timestamp": "2026-07-15T10:00:00Z",
            }
        """
        # Normalise metadata: convert any list/dict values to JSON strings
        # because ChromaDB does not accept complex types in metadata fields.
        safe_meta: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, (list, dict)):
                safe_meta[key] = json.dumps(value)
            elif isinstance(value, (str, int, float, bool)) or value is None:
                safe_meta[key] = value if value is not None else ""
            else:
                safe_meta[key] = str(value)

        embedding = self.embed_text(text)

        self.collection.upsert(
            ids=[capture_id],
            embeddings=[embedding],
            documents=[text],
            metadatas=[safe_meta],
        )

    # ─── Queries ─────────────────────────────────────────────────────────────

    def query_similar(self, text: str, k: int = TOP_K_RETRIEVAL) -> list[dict]:
        """Return the *k* most semantically similar notes to *text*.

        Args:
            text: Query string.
            k:    Number of results to return (default: TOP_K_RETRIEVAL).

        Returns:
            A list of result dicts, each containing::

                {
                    "id":         str,   # capture ID
                    "document":   str,   # stored text
                    "metadata":   dict,  # stored metadata
                    "similarity": float, # cosine similarity (0–1, higher = better)
                }

            The list is ordered by descending similarity.

        Notes:
            - Returns an empty list if the collection is empty.
            - ChromaDB returns *distance* (0 = identical, 2 = opposite for
              cosine); we convert it to similarity = 1 − distance.
        """
        if self.collection.count() == 0:
            return []

        # ChromaDB limits n_results to the number of items in the collection
        n = min(k, self.collection.count())

        query_embedding = self.embed_text(text)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n,
            include=["documents", "metadatas", "distances"],
        )

        return self._format_results(results)

    def query_similar_by_id(
        self, capture_id: str, k: int = TOP_K_RETRIEVAL
    ) -> list[dict]:
        """Return the *k* most similar notes to an *existing* note by its ID.

        Args:
            capture_id: The ID of the note to use as the query anchor.
            k:          Number of results to return (excluding the note itself).

        Returns:
            Same format as :meth:`query_similar`.  The source note itself is
            excluded from the results.

        Raises:
            ValueError: If *capture_id* is not found in the collection.
        """
        # Fetch the stored document so we can re-embed from its text
        fetched = self.collection.get(
            ids=[capture_id],
            include=["documents"],
        )
        if not fetched["ids"]:
            raise ValueError(
                f"capture_id '{capture_id}' not found in the ChromaDB collection. "
                "Make sure the note has been stored via engine.store() first."
            )

        source_text: str = fetched["documents"][0]

        # Fetch k+1 so we can drop the self-match
        raw_results = self.query_similar(source_text, k=k + 1)

        # Remove the source note from the results
        return [r for r in raw_results if r["id"] != capture_id][:k]

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _format_results(chroma_results: dict) -> list[dict]:
        """Convert raw ChromaDB query output into the project's result format.

        ChromaDB returns distances in *cosine distance* space (0–2).
        We convert: ``similarity = 1 − distance``.
        """
        formatted: list[dict] = []

        ids = chroma_results.get("ids", [[]])[0]
        documents = chroma_results.get("documents", [[]])[0]
        metadatas = chroma_results.get("metadatas", [[]])[0]
        distances = chroma_results.get("distances", [[]])[0]

        for doc_id, document, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            # Clamp to [0, 1] to guard against any floating-point edge cases
            similarity = max(0.0, min(1.0, 1.0 - distance))
            formatted.append(
                {
                    "id": doc_id,
                    "document": document,
                    "metadata": metadata,
                    "similarity": round(similarity, 4),
                }
            )

        # Already sorted by ascending distance (= descending similarity) by ChromaDB
        return formatted
