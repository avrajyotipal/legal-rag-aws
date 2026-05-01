"""
Calls Amazon Nova Pro on AWS Bedrock to generate a grounded, citation-aware answer.
The model is instructed to answer strictly from the provided context chunks.
"""
import json

from shared.aws_clients import get_bedrock_client
from shared.config import BEDROCK_LLM_MODEL_ID
from shared.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are a precise legal research assistant. "
    "Answer the user's question using ONLY the document excerpts provided. "
    "Cite every claim with [Source N] where N matches the excerpt number. "
    "If the answer is not found in the excerpts, state that clearly — do not speculate."
)


def generate_answer(query: str, top_chunks: list[dict]) -> dict:
    citations: list[dict] = []
    context_blocks: list[str] = []

    for i, chunk in enumerate(top_chunks, start=1):
        src = chunk["source"]
        citations.append({
            "index":       i,
            "source_file": src.get("source_file", "unknown"),
            "page":        src.get("page_number", "?"),
            "section":     src.get("section_heading", ""),
            "s3_key":      src.get("s3_key", ""),
            "score":       round(chunk.get("final_score", 0.0), 4),
        })
        header = (
            f"[Source {i}] File: {src.get('source_file', '?')} | "
            f"Page: {src.get('page_number', '?')}"
        )
        if src.get("section_heading"):
            header += f" | Section: {src['section_heading']}"
        context_blocks.append(f"{header}\n{src.get('chunk_text', '')}")

    context = "\n\n---\n\n".join(context_blocks)
    user_message = (
        f"Document excerpts:\n\n{context}\n\n"
        f"---\n\nQuestion: {query}\n\n"
        "Answer using only the excerpts above. Cite sources as [Source N]."
    )

    body = json.dumps({
        "messages": [{"role": "user", "content": [{"text": user_message}]}],
        "system":   [{"text": _SYSTEM_PROMPT}],
        "inferenceConfig": {
            "maxTokens":   2048,
            "temperature": 0.1,
            "topP":        0.9,
        },
    })

    bedrock = get_bedrock_client()
    resp = bedrock.invoke_model(
        modelId=BEDROCK_LLM_MODEL_ID,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    resp_body = json.loads(resp["body"].read())
    answer_text = resp_body["output"]["message"]["content"][0]["text"]

    logger.info(f"Answer generated ({len(answer_text)} chars, {len(citations)} citations)")
    return {
        "answer":    answer_text,
        "citations": citations,
        "model":     BEDROCK_LLM_MODEL_ID,
    }
