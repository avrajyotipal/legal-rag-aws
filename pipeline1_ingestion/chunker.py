"""
Splits extracted page text into overlapping token-based chunks and attaches full metadata.
Uses tiktoken (cl100k_base) for token counting to stay consistent with modern LLMs.
"""
import hashlib
from datetime import datetime, timezone

import tiktoken

from shared.config import CHUNK_SIZE, CHUNK_OVERLAP
from shared.logger import get_logger

logger = get_logger(__name__)
_enc = tiktoken.get_encoding("cl100k_base")


def chunk_pages(pages: list[dict], s3_key: str, etag: str) -> list[dict]:
    """
    Returns a flat list of chunk dicts ready for embedding and indexing.
    Each chunk carries all provenance metadata needed for citation.
    """
    source_file = s3_key.split("/")[-1]
    chunks: list[dict] = []
    chunk_index = 0

    for page in pages:
        tokens = _enc.encode(page["text"])
        start = 0

        while start < len(tokens):
            end = min(start + CHUNK_SIZE, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = _enc.decode(chunk_tokens).strip()

            if chunk_text:
                content_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                chunks.append({
                    "chunk_text":         chunk_text,
                    "content_hash":       content_hash,
                    "file_hash":          etag,
                    "source_file":        source_file,
                    "s3_key":             s3_key,
                    "page_number":        page["page_number"],
                    "section_heading":    page.get("section_heading", ""),
                    "chunk_index":        chunk_index,
                    "uploader":           page.get("uploader", "unknown"),
                    "ingestion_timestamp": datetime.now(timezone.utc).isoformat(),
                })
                chunk_index += 1

            if end == len(tokens):
                break
            start += CHUNK_SIZE - CHUNK_OVERLAP

    logger.info(
        f"Chunked '{source_file}': {len(pages)} page segment(s) -> {len(chunks)} chunks"
        f" (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})"
    )
    return chunks
