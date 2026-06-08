"""
Task 9 — Retrieval Pipeline Hoàn Chỉnh.

Pipeline:
    Query
      ├→ Semantic Search (task5)  ──┐
      │                              ├→ RRF Merge (task7) → Reranked Results
      ├→ Lexical Search (task6)  ──┘
      │
      └→ If best_score < score_threshold:
            └→ Fallback: PageIndex Vectorless (task8)

Score threshold logic:
    - Hybrid RRF scores thường trong range [0.001, 0.02]
    - Dùng score_threshold=0.005 để catch các trường hợp không tìm thấy gì
    - Nếu cả hybrid lẫn pageindex không có kết quả → trả về []
"""

import logging
import os

os.environ.setdefault("USE_TF", "0")

log = logging.getLogger(__name__)

# Import với fallback cho cả relative (package) lẫn absolute (standalone) import
try:
    from src.task5_semantic_search import semantic_search
    from src.task6_lexical_search import lexical_search
    from src.task7_reranking import rerank, rerank_rrf
    from src.task8_pageindex_vectorless import pageindex_search
except ImportError:
    from task5_semantic_search import semantic_search
    from task6_lexical_search import lexical_search
    from task7_reranking import rerank, rerank_rrf
    from task8_pageindex_vectorless import pageindex_search

# =============================================================================
# CONFIGURATION
# =============================================================================

# RRF scores thường rất nhỏ (~0.01), dùng threshold nhỏ để detect "no results"
SCORE_THRESHOLD = 0.005
DEFAULT_TOP_K = 5


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float = SCORE_THRESHOLD,
    use_reranking: bool = True,
) -> list[dict]:
    """
    Retrieval pipeline hoàn chỉnh với fallback logic.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả cuối cùng
        score_threshold: Ngưỡng điểm tối thiểu (dưới ngưỡng → fallback PageIndex)
        use_reranking: Có áp dụng RRF reranking hay không

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict,
            'source': str  # 'hybrid' hoặc 'pageindex'
        }
    """
    log.info(f"Retrieve: '{query[:60]}...' (top_k={top_k}, threshold={score_threshold})")

    # Step 1: Run semantic + lexical search in parallel (conceptually)
    # Lấy gấp đôi top_k để có đủ candidates cho RRF
    fetch_k = top_k * 3

    dense_results = semantic_search(query, top_k=fetch_k)
    sparse_results = lexical_search(query, top_k=fetch_k)

    log.info(f"  Dense: {len(dense_results)} results, Sparse: {len(sparse_results)} results")

    # Step 2: Merge bằng RRF
    all_lists = [l for l in [dense_results, sparse_results] if l]

    if not all_lists:
        log.warning("  Both semantic and lexical returned empty — trying PageIndex fallback")
        return _pageindex_fallback(query, top_k)

    if len(all_lists) == 1:
        merged = all_lists[0][:top_k * 2]
        for item in merged:
            item["source"] = "hybrid"
    else:
        merged = rerank_rrf(all_lists, top_k=top_k * 2)
        for item in merged:
            item["source"] = "hybrid"

    log.info(f"  Merged (RRF): {len(merged)} candidates")

    # Step 3: Rerank
    if use_reranking and merged:
        final_results = rerank(query, merged, top_k=top_k, method="rrf")
    else:
        final_results = merged[:top_k]

    log.info(f"  After rerank: {len(final_results)} results")

    # Step 4: Check threshold → fallback
    if not final_results or final_results[0]["score"] < score_threshold:
        best_score = final_results[0]["score"] if final_results else 0
        log.warning(
            f"  Best score ({best_score:.6f}) < threshold ({score_threshold}). "
            f"Fallback → PageIndex"
        )
        fallback = _pageindex_fallback(query, top_k)
        if fallback:
            return fallback

    return final_results[:top_k]


def _pageindex_fallback(query: str, top_k: int) -> list[dict]:
    """PageIndex fallback với graceful degradation."""
    try:
        results = pageindex_search(query, top_k=top_k)
        if results:
            log.info(f"  PageIndex fallback: {len(results)} results")
        else:
            log.info("  PageIndex fallback: no results (API key missing or no data)")
        return results
    except Exception as e:
        log.error(f"  PageIndex fallback failed: {e}")
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý",
        "Nghệ sĩ nào bị bắt vì sử dụng ma tuý",
        "Luật phòng chống ma tuý 2021 quy định gì về cai nghiện",
        "xyzabc123nonsense",  # Test fallback
    ]

    for q in test_queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        print("-" * 60)
        results = retrieve(q, top_k=3)
        if not results:
            print("  (no results)")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['score']:.6f}] [{r['source']}] {r['content'][:80]}...")
