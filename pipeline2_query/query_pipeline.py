"""
Pipeline 2 orchestrator — single entry point for the chat interface.
Flow: embed query → hybrid search → re-rank → LLM → structured response.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline2_query.query_embedder import embed_query
from pipeline2_query.searcher import hybrid_search
from pipeline2_query.reranker import rerank
from pipeline2_query.llm_caller import generate_answer
from shared.logger import get_logger

logger = get_logger("query_pipeline")

_NO_RESULTS_RESPONSE = {
    "answer": (
        "No relevant documents were found in the knowledge base for your query. "
        "Please ensure relevant legal documents have been uploaded and indexed."
    ),
    "citations": [],
    "model": "",
}


def run_query(user_query: str) -> dict:
    logger.info(f"Query received: {user_query[:120]!r}")

    query_embedding = embed_query(user_query)
    candidates = hybrid_search(query_embedding, user_query)

    if not candidates:
        logger.warning("No candidates returned from OpenSearch")
        return _NO_RESULTS_RESPONSE

    top_chunks = rerank(candidates)
    result = generate_answer(user_query, top_chunks)

    return result
