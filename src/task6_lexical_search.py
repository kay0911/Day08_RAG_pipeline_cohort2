"""
Task 6 — Lexical Search Module (BM25).

BM25 hoạt động:
- TF (Term Frequency): từ xuất hiện nhiều trong doc → score cao
- IDF (Inverse Doc Frequency): từ hiếm → quan trọng hơn
- Length normalization: doc dài không được ưu tiên quá mức
- Formula: Σ IDF(qi) * tf(qi,d)*(k1+1) / (tf(qi,d) + k1*(1-b+b*|d|/avgdl))
- k1=1.5 (term saturation), b=0.75 (length normalization)

Corpus được load từ data/standardized/ và index lại BM25 mỗi lần khởi động
(hoặc được cache). Vietnamese tokenization dùng simple whitespace split —
đủ hiệu quả vì BM25 chủ yếu dựa trên term matching.
"""

import logging
from pathlib import Path

log = logging.getLogger(__name__)

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"

# Module-level corpus và BM25 index (lazy-initialized)
_corpus: list[dict] = []
_bm25 = None
_bm25_ready = False


def _load_corpus() -> list[dict]:
    """Load documents từ data/standardized/ làm BM25 corpus."""
    # Reuse chunks từ task4 nếu có; fallback sang raw markdown files
    try:
        from src.task4_chunking_indexing import _get_collection

        collection = _get_collection()
        if collection.count() > 0:
            results = collection.get(include=["documents", "metadatas"])
            corpus = []
            for doc, meta in zip(results["documents"], results["metadatas"]):
                corpus.append({"content": doc, "metadata": meta or {}})
            log.info(f"BM25 corpus loaded from ChromaDB: {len(corpus)} chunks")
            return corpus
    except Exception as e:
        log.debug(f"ChromaDB not available for BM25 corpus: {e}")

    # Fallback: load từ markdown files trực tiếp và chunk đơn giản
    corpus = []
    if not STANDARDIZED_DIR.exists():
        return corpus

    for md_file in STANDARDIZED_DIR.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        doc_type = "legal" if "legal" in str(md_file) else "news"
        # Simple paragraph chunking for BM25
        paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 50]
        for i, para in enumerate(paragraphs):
            corpus.append({
                "content": para,
                "metadata": {
                    "source": md_file.name,
                    "type": doc_type,
                    "chunk_index": i,
                }
            })

    log.info(f"BM25 corpus loaded from markdown files: {len(corpus)} chunks")
    return corpus


def _ensure_bm25_ready() -> bool:
    """Lazy-initialize BM25 index."""
    global _corpus, _bm25, _bm25_ready
    if _bm25_ready:
        return True

    from rank_bm25 import BM25Okapi

    _corpus = _load_corpus()
    if not _corpus:
        log.warning("Empty corpus — BM25 index not built. Run tasks 1-4 first.")
        return False

    tokenized_corpus = [doc["content"].lower().split() for doc in _corpus]
    _bm25 = BM25Okapi(tokenized_corpus)
    _bm25_ready = True
    log.info(f"BM25 index built with {len(_corpus)} documents")
    return True


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm từ khóa sử dụng BM25Okapi.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,   # BM25 score (unnormalized)
            'metadata': dict
        }
        Sorted by score descending, score > 0 only.
    """
    import numpy as np

    if not _ensure_bm25_ready():
        return []

    tokenized_query = query.lower().split()
    scores = _bm25.get_scores(tokenized_query)

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score <= 0:
            break  # BM25 scores are 0 for non-matching docs
        results.append({
            "content": _corpus[idx]["content"],
            "score": round(score, 4),
            "metadata": _corpus[idx]["metadata"],
        })

    return results


def rebuild_index() -> None:
    """Force rebuild BM25 index (dùng sau khi thêm documents mới)."""
    global _bm25_ready
    _bm25_ready = False
    _ensure_bm25_ready()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    queries = [
        "Điều 248 tàng trữ trái phép chất ma tuý hình phạt",
        "cai nghiện bắt buộc 12 tháng 24 tháng",
        "Châu Việt Cường bị bắt ma tuý",
    ]
    for q in queries:
        print(f"\nQuery: {q}")
        results = lexical_search(q, top_k=3)
        if not results:
            print("  (no results)")
        for r in results:
            print(f"  [{r['score']:.3f}] {r['content'][:80]}...")
