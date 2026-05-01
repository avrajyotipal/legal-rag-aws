"""
Deduplication layer between the embedding step and OpenSearch.
Checks content_hash before every insert — no duplicate chunks ever reach the index.
"""
from shared.aws_clients import get_opensearch_client
from shared.config import OPENSEARCH_INDEX
from shared.logger import get_logger

logger = get_logger(__name__)


def _hash_exists(client, content_hash: str) -> bool:
    resp = client.search(
        index=OPENSEARCH_INDEX,
        body={
            "query": {"term": {"content_hash": content_hash}},
            "_source": False,
            "size": 1,
        },
    )
    return resp["hits"]["total"]["value"] > 0


def store_chunks(chunks: list[dict]) -> dict:
    """
    Inserts chunks that are not already present in OpenSearch.
    Returns counts of inserted and skipped chunks.
    """
    client = get_opensearch_client()
    inserted = 0
    skipped = 0

    for chunk in chunks:
        if _hash_exists(client, chunk["content_hash"]):
            logger.debug(f"Duplicate — skipping chunk hash {chunk['content_hash'][:12]}")
            skipped += 1
            continue

        client.index(index=OPENSEARCH_INDEX, body=chunk)
        inserted += 1

    logger.info(f"OpenSearch write complete: {inserted} inserted, {skipped} skipped (duplicates)")
    return {"inserted": inserted, "skipped": skipped}
