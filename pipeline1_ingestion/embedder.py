"""
Calls AWS Bedrock Titan Embeddings V2 to produce 1024-dim normalized vectors.
Processes chunks sequentially with a small inter-batch delay to respect rate limits.
"""
import json
import time

from shared.aws_clients import get_bedrock_client
from shared.config import BEDROCK_EMBEDDING_MODEL_ID, BEDROCK_EMBEDDING_DIMENSIONS
from shared.logger import get_logger

logger = get_logger(__name__)

_MAX_INPUT_CHARS = 25_000  # Titan V2 comfortable limit (well under 8k tokens)
_LOG_EVERY = 20            # log progress every N chunks


def embed_text(text: str) -> list[float]:
    bedrock = get_bedrock_client()
    body = json.dumps({
        "inputText": text[:_MAX_INPUT_CHARS],
        "dimensions": BEDROCK_EMBEDDING_DIMENSIONS,
        "normalize": True,
    })
    resp = bedrock.invoke_model(
        modelId=BEDROCK_EMBEDDING_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]


def embed_chunks(chunks: list[dict], inter_batch_delay: float = 0.05) -> list[dict]:
    """
    Adds 'embedding' field to each chunk in-place.
    Chunks that fail embedding are dropped from the returned list.
    """
    succeeded: list[dict] = []
    for i, chunk in enumerate(chunks, start=1):
        try:
            chunk["embedding"] = embed_text(chunk["chunk_text"])
            succeeded.append(chunk)
        except Exception as exc:
            logger.error(f"Embedding failed for chunk {i}/{len(chunks)}: {exc}")
            continue

        if i % _LOG_EVERY == 0:
            logger.info(f"Embedded {i}/{len(chunks)} chunks")
            time.sleep(inter_batch_delay)

    logger.info(f"Embedding complete: {len(succeeded)}/{len(chunks)} chunks succeeded")
    return succeeded
