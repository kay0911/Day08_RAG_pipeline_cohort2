"""
Task 5 — Semantic Search Module.

Queries ChromaDB collection built in Task 4.
Uses the same BAAI/bge-m3 embedding model to encode the query.
Returns results sorted by cosine similarity (descending).
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Reuse singletons from task4 to avoid double-loading the model
_semantic_ready = False


def _ensure_index_ready():
    """Check ChromaDB có dữ liệu chưa; nếu chưa thì index."""
    global _semantic_ready
    if _semantic_ready:
        return True

    from src.task4_chunking_indexing import _get_collection
    try:
        collection = _get_collection()
        if collection.count() == 0:
            log.warning("ChromaDB is empty. Run task4 first (or indexing now).")
            return False
        _semantic_ready = True
        return True
    except Exception as e:
        log.error(f"ChromaDB not ready: {e}")
        return False


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng vector similarity (cosine) trên ChromaDB.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,   # cosine similarity [0, 1]
            'metadata': dict
        }
        Sorted by score descending.
    """
    if not _ensure_index_ready():
        return []

    from src.task4_chunking_indexing import _get_embedding_model, _get_collection

    model = _get_embedding_model()
    collection = _get_collection()

    query_embedding = model.encode(query).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    docs = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(docs, metadatas, distances):
        # ChromaDB cosine distance: distance = 1 - similarity
        score = max(0.0, 1.0 - dist)
        output.append({
            "content": doc,
            "score": round(score, 4),
            "metadata": meta or {},
        })

    # Already sorted by distance (ascending) → similarity (descending)
    return output


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    queries = [
        "hình phạt cho tội tàng trữ ma tuý",
        "cai nghiện bắt buộc theo luật 2021",
        "nghệ sĩ bị bắt vì sử dụng ma tuý",
    ]
    for q in queries:
        print(f"\nQuery: {q}")
        results = semantic_search(q, top_k=3)
        for r in results:
            print(f"  [{r['score']:.3f}] [{r['metadata'].get('type','?')}] {r['content'][:80]}...")
