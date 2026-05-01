import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / "infra" / "config.env"
load_dotenv(dotenv_path=_env_path)

AWS_REGION               = os.getenv("AWS_REGION", "us-east-1")

# Application uses service account credentials; fall back to admin creds if SVC not yet created
SVC_ACCESS_KEY_ID        = os.getenv("SVC_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
SVC_SECRET_ACCESS_KEY    = os.getenv("SVC_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")

S3_BUCKET_NAME           = os.getenv("S3_BUCKET_NAME", "legal-rag-documents")
OPENSEARCH_ENDPOINT      = os.getenv("OPENSEARCH_ENDPOINT", "")
OPENSEARCH_INDEX         = os.getenv("OPENSEARCH_INDEX", "legal-docs")

BEDROCK_EMBEDDING_MODEL_ID  = os.getenv("BEDROCK_EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v2:0")
BEDROCK_EMBEDDING_DIMENSIONS = int(os.getenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024"))
BEDROCK_LLM_MODEL_ID        = os.getenv("BEDROCK_LLM_MODEL_ID", "amazon.nova-pro-v1:0")

CHUNK_SIZE               = int(os.getenv("CHUNK_SIZE", "512"))
CHUNK_OVERLAP            = int(os.getenv("CHUNK_OVERLAP", "64"))
TOP_K                    = int(os.getenv("TOP_K", "5"))
RERANK_ALPHA             = float(os.getenv("RERANK_ALPHA", "0.7"))
PRE_RERANK_K             = int(os.getenv("PRE_RERANK_K", "10"))
