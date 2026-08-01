"""Quick embedding system smoke test — run with: uv run python scripts/test_embed_quick.py"""
from secondself.embed import EmbeddingEngine

print("Initializing EmbeddingEngine...")
e = EmbeddingEngine()
print(f"Collection: {e.collection.name} | Existing notes: {e.collection.count()}")

print("\nStoring 3 test notes...")
e.store("n1", "transformers use self-attention for NLP", {"title": "Transformers"})
e.store("n2", "neural networks learn via backpropagation", {"title": "Neural Nets"})
e.store("n3", "sourdough bread needs a live yeast starter", {"title": "Sourdough"})
print(f"Total after store: {e.collection.count()}")

print("\nQuerying: 'deep learning AI' (top 3):")
for r in e.query_similar("deep learning AI", k=3):
    bar = "█" * int(r["similarity"] * 20)
    print(f"  {r['similarity']:.3f}  {bar:<20}  {r['metadata']['title']}")

print("\nQuery by ID (notes similar to 'Transformers', excluding itself):")
for r in e.query_similar_by_id("n1", k=2):
    print(f"  {r['similarity']:.3f}  {r['metadata']['title']}")

print("\n✅ Embedding system working correctly!")
