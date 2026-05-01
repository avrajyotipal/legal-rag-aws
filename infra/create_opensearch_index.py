"""
Creates the legal-docs k-NN index on AWS OpenSearch.
Run after setup_opensearch.sh has saved the endpoint to config.env.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.aws_clients import get_opensearch_client
from shared.config import OPENSEARCH_INDEX, BEDROCK_EMBEDDING_DIMENSIONS
from shared.logger import get_logger

logger = get_logger("create_index")

INDEX_BODY = {
    "settings": {
        "index": {
            "knn": True,
            "knn.algo_param.ef_search": 512,
            "number_of_shards": 1,
            "number_of_replicas": 0,
        }
    },
    "mappings": {
        "properties": {
            "chunk_text": {
                "type": "text",
                "analyzer": "english",
                "fields": {"keyword": {"type": "keyword", "ignore_above": 512}},
            },
            "embedding": {
                "type": "knn_vector",
                "dimension": BEDROCK_EMBEDDING_DIMENSIONS,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "nmslib",
                    "parameters": {"ef_construction": 512, "m": 16},
                },
            },
            "content_hash":        {"type": "keyword"},
            "file_hash":           {"type": "keyword"},
            "source_file":         {"type": "keyword"},
            "s3_key":              {"type": "keyword"},
            "page_number":         {"type": "integer"},
            "section_heading":     {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "chunk_index":         {"type": "integer"},
            "uploader":            {"type": "keyword"},
            "ingestion_timestamp": {"type": "date"},
        }
    },
}


def main():
    client = get_opensearch_client()

    if client.indices.exists(index=OPENSEARCH_INDEX):
        logger.info(f"Index '{OPENSEARCH_INDEX}' already exists — skipping creation.")
        return

    logger.info(f"Creating index '{OPENSEARCH_INDEX}' with {BEDROCK_EMBEDDING_DIMENSIONS}-dim k-NN vectors...")
    resp = client.indices.create(index=OPENSEARCH_INDEX, body=INDEX_BODY)
    logger.info(f"Index created: {resp}")


if __name__ == "__main__":
    main()
