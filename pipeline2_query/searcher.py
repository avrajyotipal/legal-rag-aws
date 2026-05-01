"""
Hybrid search over OpenSearch: combines k-NN vector search with BM25 keyword search.
Results from both searches are merged into a single candidate pool for re-ranking.
"""
from shared.aws_clients import get_opensearch_client
from shared.config import OPENSEARCH_INDEX, PRE_RERANK_K, TOP_K
from shared.logger import get_logger

logger = get_logger(__name__)

_CANDIDATE_FACTOR = 3  # fetch this many × TOP_K candidates before re-ranking


def hybrid_search(query_embedding: list[float], query_text: str) -> list[dict]:
    client = get_opensearch_client()
    fetch_k = max(TOP_K * _CANDIDATE_FACTOR, PRE_RERANK_K)

    knn_hits = _knn_search(client, query_embedding, fetch_k)
    bm25_hits = _bm25_search(client, query_text, fetch_k)

    merged = _merge(knn_hits, bm25_hits)
    logger.info(
        f"Hybrid search: knn={len(knn_hits)} + bm25={len(bm25_hits)} → merged={len(merged)} candidates"
    )
    return merged


def _knn_search(client, embedding: list[float], k: int) -> dict[str, dict]:
    resp = client.search(
        index=OPENSEARCH_INDEX,
        body={
            "size": k,
            "query": {"knn": {"embedding": {"vector": embedding, "k": k}}},
            "_source": {"excludes": ["embedding"]},
        },
    )
    results = {}
    for hit in resp["hits"]["hits"]:
        results[hit["_id"]] = {
            "doc_id":   hit["_id"],
            "source":   hit["_source"],
            "knn_score":  float(hit["_score"] or 0.0),
            "bm25_score": 0.0,
        }
    return results


def _bm25_search(client, query_text: str, k: int) -> dict[str, dict]:
    resp = client.search(
        index=OPENSEARCH_INDEX,
        body={
            "size": k,
            "query": {
                "match": {
                    "chunk_text": {"query": query_text, "operator": "or"}
                }
            },
            "_source": {"excludes": ["embedding"]},
        },
    )
    results = {}
    for hit in resp["hits"]["hits"]:
        results[hit["_id"]] = {
            "doc_id":     hit["_id"],
            "source":     hit["_source"],
            "knn_score":  0.0,
            "bm25_score": float(hit["_score"] or 0.0),
        }
    return results


def _merge(knn: dict, bm25: dict) -> list[dict]:
    merged: dict[str, dict] = {}
    for doc_id, data in knn.items():
        merged[doc_id] = data.copy()
    for doc_id, data in bm25.items():
        if doc_id in merged:
            merged[doc_id]["bm25_score"] = data["bm25_score"]
        else:
            merged[doc_id] = data.copy()
    return list(merged.values())
