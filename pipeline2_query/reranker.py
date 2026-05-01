"""
Custom re-ranker: blends normalized semantic (knn) and keyword (BM25) scores.

final_score = α × norm_knn_score + (1 − α) × norm_bm25_score

α = RERANK_ALPHA (default 0.7 — semantic-dominant for legal text while
preserving exact-term match signals from BM25).
"""
from shared.config import RERANK_ALPHA, TOP_K
from shared.logger import get_logger

logger = get_logger(__name__)


def rerank(candidates: list[dict]) -> list[dict]:
    if not candidates:
        return []

    knn_scores  = [c["knn_score"]  for c in candidates]
    bm25_scores = [c["bm25_score"] for c in candidates]

    knn_max  = max(knn_scores)  if max(knn_scores)  > 0 else 1.0
    bm25_max = max(bm25_scores) if max(bm25_scores) > 0 else 1.0

    for c in candidates:
        norm_knn  = c["knn_score"]  / knn_max
        norm_bm25 = c["bm25_score"] / bm25_max
        c["final_score"] = RERANK_ALPHA * norm_knn + (1.0 - RERANK_ALPHA) * norm_bm25

    ranked = sorted(candidates, key=lambda x: x["final_score"], reverse=True)
    top = ranked[:TOP_K]

    logger.info(
        f"Re-ranked {len(candidates)} candidates → top {len(top)} "
        f"(α={RERANK_ALPHA}, top score={top[0]['final_score']:.4f})"
    )
    return top
