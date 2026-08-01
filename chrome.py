
from secondself.embed import EmbeddingEngine
e = EmbeddingEngine()
e.store(
    'my-capture-id',
    'Text content to embed and store',
    {
        'category': 'resources',
        'tags': '[\"ai\", \"nlp\"]',
        'title': 'My Note Title',
        'timestamp': '2026-07-15T10:00:00Z',
    }
)
print('Stored. Total in ChromaDB:', e.collection.count())