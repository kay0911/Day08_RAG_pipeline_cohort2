"""
Task 7 — Reranking Module.

Phương pháp: RRF (Reciprocal Rank Fusion) — Cormack et al. 2009.

RRF(d) = Σ_r 1 / (k + rank_r(d))

k=60 là hằng số làm mượt (smoothing constant) được đề xuất trong paper gốc.
RRF không cần training, không cần API, hoạt động tốt khi gộp nhiều ranker.

unified rerank() interface:
    - Nhận candidates list (từ 1 ranker)
    - Tạo BM25 re-ranking trên tập candidates đó
    - Apply RRF để fuse original ranking + BM25 ranking
    - Trả về top_k re-ordered candidates
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)


def rerank_rrf(
    ranked_lists: list[list[dict]],
    top_k: int = 5,
    k: int = 60,
) -> list[dict]:
    """
    Reciprocal Rank Fusion — gộp kết quả từ nhiều ranker.

    RRF score(d) = Σ 1 / (k + rank_r(d))
    k=60: smoothing constant (Cormack et al. 2009) làm giảm ảnh hưởng
    của top ranks so với bottom ranks, giúp RRF ổn định hơn.

    Args:
        ranked_lists: List of ranked result lists (mỗi list từ 1 ranker)
        top_k: Số lượng kết quả cuối cùng
        k: Smoothing constant

    Returns:
        List of top_k candidates sorted by RRF score descending.
        Mỗi item có 'score' là RRF score.
    """
    rrf_scores: dict[str, float] = {}
    # Map content → first occurrence dict (preserve all metadata)
    content_map: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, 1):
            key = item["content"]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in content_map:
                content_map[key] = item

    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for content, score in sorted_items[:top_k]:
        item = {**content_map[content], "score": round(score, 6)}
        results.append(item)

    return results


def rerank_mmr(
    query_embedding: list[float],
    candidates: list[dict],
    top_k: int = 5,
    lambda_param: float = 0.7,
) -> list[dict]:
    """
    Maximal Marginal Relevance — balance relevance và diversity.

    MMR(d) = λ·sim(query, d) - (1-λ)·max_{d'∈S} sim(d, d')
    λ=0.7: weight relevance 70% vs diversity 30%.

    Args:
        query_embedding: Vector embedding của query
        candidates: List of {'content', 'score', 'embedding', 'metadata'}
        top_k: Số lượng kết quả
        lambda_param: 1.0=max relevance, 0.0=max diversity

    Returns:
        List of top_k candidates selected by MMR.
    """
    import numpy as np

    if not candidates:
        return []

    def cosine_sim(a, b):
        a, b = np.array(a), np.array(b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0

    selected_indices = []
    remaining = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_idx = None
        best_score = float("-inf")

        for idx in remaining:
            emb = candidates[idx].get("embedding", [])
            if not emb:
                # Fallback: use existing score as relevance
                relevance = candidates[idx].get("score", 0.0)
            else:
                relevance = cosine_sim(query_embedding, emb)

            max_sim_selected = 0.0
            for sel_idx in selected_indices:
                sel_emb = candidates[sel_idx].get("embedding", [])
                if emb and sel_emb:
                    sim = cosine_sim(emb, sel_emb)
                    max_sim_selected = max(max_sim_selected, sim)

            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim_selected

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx is not None:
            selected_indices.append(best_idx)
            remaining.remove(best_idx)

    return [
        {**candidates[i], "score": round(candidates[i].get("score", 0.0), 4)}
        for i in selected_indices
    ]


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    method: str = "rrf",
) -> list[dict]:
    """
    Unified reranking interface.

    Với method="rrf":
        1. Tạo BM25 re-ranking trên tập candidates (second ranker)
        2. Apply RRF để fuse original ranking + BM25 ranking
        Kết quả: items được boost nếu tốt ở cả 2 ranker (original score + keyword match)

    Args:
        query: Câu truy vấn
        candidates: Danh sách candidates từ retrieval (1 ranked list)
        top_k: Số lượng kết quả sau rerank
        method: "rrf" (default) | "mmr"

    Returns:
        List of top_k reranked candidates.
    """
    if not candidates:
        return []

    if method == "rrf":
        # Create BM25-based second ranking on the candidate set
        bm25_ranked = _bm25_rank_candidates(query, candidates)
        # Fuse original ranking with BM25 ranking via RRF
        return rerank_rrf([candidates, bm25_ranked], top_k=top_k)

    elif method == "mmr":
        # MMR needs embeddings — use scores as proxy if embeddings not available
        return rerank_mmr([], candidates, top_k=top_k)

    else:
        raise ValueError(f"Unknown rerank method: {method}. Use 'rrf' or 'mmr'.")


def _bm25_rank_candidates(query: str, candidates: list[dict]) -> list[dict]:
    """BM25 score on candidates để dùng làm second ranker trong RRF."""
    from rank_bm25 import BM25Okapi
    import numpy as np

    if not candidates:
        return []

    tokenized_corpus = [c["content"].lower().split() for c in candidates]
    bm25 = BM25Okapi(tokenized_corpus)
    scores = bm25.get_scores(query.lower().split())
    ranked_indices = np.argsort(scores)[::-1]
    return [candidates[i] for i in ranked_indices]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    dummy_candidates = [
        {"content": "Điều 249: Tội tàng trữ trái phép chất ma tuý, phạt tù từ 1-5 năm", "score": 0.8, "metadata": {}},
        {"content": "Nghệ sĩ X bị bắt tại TP.HCM vì sử dụng ma tuý đá", "score": 0.7, "metadata": {}},
        {"content": "Hình phạt tù từ 2-7 năm cho tội tàng trữ ma tuý số lượng lớn", "score": 0.6, "metadata": {}},
        {"content": "Python là ngôn ngữ lập trình phổ biến", "score": 0.3, "metadata": {}},
    ]

    print("=== RRF Reranking ===")
    results = rerank("hình phạt tàng trữ ma tuý", dummy_candidates, top_k=3, method="rrf")
    for r in results:
        print(f"  [{r['score']:.6f}] {r['content'][:70]}...")
