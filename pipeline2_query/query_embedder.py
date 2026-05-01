"""
Embeds a user query using the same Titan V2 model used during ingestion.
Identical model + parameters ensures vector space compatibility.
"""
import json

from shared.aws_clients import get_bedrock_client
from shared.config import BEDROCK_EMBEDDING_MODEL_ID, BEDROCK_EMBEDDING_DIMENSIONS

_MAX_INPUT_CHARS = 25_000


def embed_query(query: str) -> list[float]:
    bedrock = get_bedrock_client()
    body = json.dumps({
        "inputText": query[:_MAX_INPUT_CHARS],
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
