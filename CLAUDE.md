# Legal RAG System — Project Blueprint

## Overview

A production-grade Retrieval-Augmented Generation (RAG) system for legal teams, built entirely on AWS services (S3, Bedrock, OpenSearch). The system has two independent but interconnected pipelines: a **Document Ingestion Pipeline** and a **Query / Chat Pipeline**. All AWS infrastructure (S3, Bedrock, OpenSearch) must be configured automatically via AWS CLI and IAM — no manual console intervention.

---

## Architecture at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                  PIPELINE 1 — Document Ingestion            │
│                                                             │
│  Legal Team UI (Upload PDF/DOCX)                            │
│       │                                                     │
│       ▼                                                     │
│  AWS S3 Bucket  ──►  File Change Detector (Lambda/Script)   │
│                            │                                │
│                            ▼  (new / unprocessed only)      │
│                       Text Extractor                        │
│                       (PDF → text, DOCX → text)             │
│                            │                                │
│                            ▼                                │
│                  Chunker + Metadata Enricher                │
│                  (chunk text, attach citations,             │
│                   source, page, section, date)              │
│                            │                                │
│                            ▼                                │
│                  AWS Bedrock Embedding Model                 │
│                  (chosen from options below)                │
│                            │                                │
│                            ▼                                │
│                  Dedup Check (hash-based)                   │
│                            │                                │
│                            ▼                                │
│                  AWS OpenSearch  ◄── Middleware Layer        │
│                  (store vectors + metadata + citations)      │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  PIPELINE 2 — Chat / Query                  │
│                                                             │
│  End-User Chat UI                                           │
│       │                                                     │
│       ▼                                                     │
│  Query Preprocessor                                         │
│  (same embedding model as Pipeline 1)                       │
│       │                                                     │
│       ▼                                                     │
│  AWS OpenSearch — Hybrid Search                             │
│  (vector similarity + BM25 keyword)                         │
│  → Retrieve top-K (default K=5) candidates                  │
│       │                                                     │
│       ▼                                                     │
│  Custom Re-ranker                                           │
│  (semantic similarity score + keyword overlap score,        │
│   configurable weight blend)                                │
│       │                                                     │
│       ▼                                                     │
│  AWS Bedrock LLM                                            │
│  (final answer generation with citations)                   │
│       │                                                     │
│       ▼                                                     │
│  Chat UI Response (answer + source citations)               │
└─────────────────────────────────────────────────────────────┘
```

---

## AWS Services Used

| Service | Purpose |
|---|---|
| **AWS S3** | Primary document store; raw PDF/DOCX files |
| **AWS Bedrock** | Embedding model + LLM inference |
| **AWS OpenSearch Service** | Vector + keyword search index |
| **AWS IAM** | Roles, policies, automated permissions |
| **AWS Lambda** (optional) | Event-driven file-change detection on S3 |

---

## Embedding Model Options (AWS Bedrock)

The user must choose one of the following. All are available via AWS Bedrock:

| # | Model | Provider | Dimensions | Notes |
|---|---|---|---|---|
| 1 | **Amazon Titan Embeddings V2** | Amazon | 1024 | Native Bedrock, lowest latency, good general-purpose |
| 2 | **Cohere Embed English v3** | Cohere | 1024 | Strong domain-specific performance, supports input types |
| 3 | **Cohere Embed Multilingual v3** | Cohere | 1024 | Best if multilingual legal docs are expected |
| 4 | **Amazon Titan Embeddings G1 — Text** | Amazon | 1536 | Older but widely used, 1536-dim |

> **Recommendation:** For English-only legal documents, **Titan Embeddings V2** or **Cohere Embed English v3** are the top picks. Cohere v3 typically edges out on legal/domain text retrieval benchmarks.

---

## LLM Options (AWS Bedrock — for Pipeline 2 answer generation)

| # | Model | Provider | Notes |
|---|---|---|---|
| 1 | **Claude Sonnet 4.6** | Anthropic | Best balance of quality and speed for RAG |
| 2 | **Claude Opus 4.7** | Anthropic | Highest quality, higher latency/cost |
| 3 | **Amazon Nova Pro** | Amazon | Cost-efficient, strong reasoning |
| 4 | **Meta Llama 3.3 70B Instruct** | Meta | Open-weight, strong instruction following |

> **Recommendation:** **Claude Sonnet 4.6** (`claude-sonnet-4-6`) for answer generation — optimized for grounded, citation-aware responses.

---

## Project Structure (Planned)

```
legal-rag-aws/
├── CLAUDE.md                        # This file
├── infra/
│   ├── setup_iam.sh                 # Create IAM roles, policies, attach permissions
│   ├── setup_s3.sh                  # Create and configure S3 bucket
│   ├── setup_opensearch.sh          # Provision OpenSearch domain
│   └── config.env                  # Centralized AWS config (region, bucket name, domain)
├── pipeline1_ingestion/
│   ├── ui/                          # Upload UI (React or simple HTML)
│   │   └── upload_app.py            # Streamlit-based upload interface
│   ├── file_watcher.py              # Detects new/unprocessed files in S3
│   ├── file_tracker.db              # SQLite or DynamoDB-backed processed file registry
│   ├── extractor.py                 # PDF + DOCX text extraction
│   ├── chunker.py                   # Text chunking + metadata enrichment
│   ├── embedder.py                  # AWS Bedrock embedding calls
│   ├── middleware.py                # Dedup logic + OpenSearch write layer
│   └── ingest_pipeline.py           # Orchestrator: watcher → extract → chunk → embed → store
├── pipeline2_query/
│   ├── ui/                          # Chat UI
│   │   └── chat_app.py              # Streamlit-based chat interface
│   ├── query_embedder.py            # Embed user query via Bedrock
│   ├── searcher.py                  # Hybrid search (vector + BM25) on OpenSearch
│   ├── reranker.py                  # Custom re-ranking (semantic + keyword blend)
│   ├── llm_caller.py                # Bedrock LLM call with context + citations
│   └── query_pipeline.py            # Orchestrator: query → embed → search → rerank → LLM
├── shared/
│   ├── aws_clients.py               # Boto3 client factory (S3, Bedrock, OpenSearch)
│   ├── config.py                    # Loads config.env
│   └── logger.py                    # Structured logging
└── requirements.txt
```

---

## Pipeline 1 — Detailed Design

### 1. Upload UI
- Streamlit app or lightweight React SPA
- Accepts PDF and DOCX files
- Uploads directly to the designated S3 bucket with a unique key (UUID + original filename)
- Records upload timestamp and uploader metadata as S3 object tags

### 2. File Change Detector
- Polls S3 (or uses S3 Event Notifications → Lambda) to detect new objects
- Maintains a **processed file registry** (SQLite locally or DynamoDB for production) keyed by S3 ETag (MD5 hash)
- Skips any file whose ETag already exists in the registry → prevents duplicate processing
- Marks files as `processing` → `done` / `failed` with timestamps

### 3. Text Extractor
- PDF: `pdfplumber` or `pypdf` — extracts text per page, preserves page numbers
- DOCX: `python-docx` — extracts paragraphs with heading context

### 4. Chunker + Metadata Enricher
- Splits text into overlapping chunks (configurable: default 512 tokens, 64-token overlap)
- Each chunk carries full metadata:
  - `source_file`: original filename
  - `s3_key`: S3 object key
  - `page_number`: page(s) the chunk came from
  - `section_heading`: nearest heading (for DOCX)
  - `chunk_index`: position within the document
  - `document_date`: extracted or inferred date
  - `uploader`: from S3 tags
  - `ingestion_timestamp`: ISO 8601

### 5. Embedding
- Calls AWS Bedrock with the chosen embedding model
- Returns a dense vector per chunk
- Batch-processes chunks to reduce API round-trips

### 6. Middleware — Dedup + Write
- Before writing to OpenSearch, computes a **content hash** (SHA-256 of chunk text)
- Checks OpenSearch for existing documents with matching `content_hash` field
- Skips insertion if duplicate found
- Inserts new documents with vector + all metadata fields

### 7. OpenSearch Index Schema
```json
{
  "mappings": {
    "properties": {
      "chunk_text":          { "type": "text", "analyzer": "english" },
      "embedding":           { "type": "knn_vector", "dimension": 1024 },
      "content_hash":        { "type": "keyword" },
      "source_file":         { "type": "keyword" },
      "s3_key":              { "type": "keyword" },
      "page_number":         { "type": "integer" },
      "section_heading":     { "type": "text" },
      "chunk_index":         { "type": "integer" },
      "document_date":       { "type": "date" },
      "uploader":            { "type": "keyword" },
      "ingestion_timestamp": { "type": "date" }
    }
  }
}
```

---

## Pipeline 2 — Detailed Design

### 1. Chat UI
- Streamlit chat interface
- Displays answer + expandable citations (source file, page, section)
- Maintains conversation history (session-scoped)

### 2. Query Embedding
- User query → same Bedrock embedding model used in Pipeline 1 → dense vector

### 3. Hybrid Search on OpenSearch
- **Vector search**: k-NN query against `embedding` field (cosine similarity), retrieve top K×2 candidates
- **BM25 keyword search**: standard `match` query on `chunk_text`, retrieve top K×2 candidates
- Merge candidate sets (union), deduplicate by document ID

### 4. Custom Re-Ranker
- For each candidate compute:
  - `semantic_score`: cosine similarity between query embedding and chunk embedding (from OpenSearch `_score`)
  - `keyword_score`: BM25 score normalized to [0, 1]
  - `final_score = α × semantic_score + (1 − α) × keyword_score`  (default α = 0.7)
- Sort by `final_score` descending, take top K (default K = 5)
- α is configurable in `config.env`

### 5. LLM Call (AWS Bedrock)
- Constructs a prompt with:
  - Retrieved chunks (numbered, with citation metadata inline)
  - Instruction to answer only from provided context and cite sources
- Calls Bedrock (chosen LLM model)
- Returns structured response: `{ "answer": "...", "citations": [...] }`

---

## Infrastructure Automation

All AWS resources are provisioned by shell scripts in `infra/`. No manual AWS Console steps are required.

### IAM Setup (`setup_iam.sh`)
- Creates a dedicated IAM role `legal-rag-role`
- Attaches inline policies for:
  - S3: `GetObject`, `PutObject`, `ListBucket` on the target bucket
  - Bedrock: `InvokeModel` for chosen embedding + LLM model ARNs
  - OpenSearch: `ESHttpGet`, `ESHttpPost`, `ESHttpPut`, `ESHttpDelete` on the target domain
- Creates an IAM user `legal-rag-svc` and attaches the role (or uses instance profile)
- Generates and stores access keys in `config.env` (gitignored)

### S3 Setup (`setup_s3.sh`)
- Creates bucket with versioning enabled
- Configures server-side encryption (SSE-S3 or SSE-KMS)
- Sets up S3 Event Notification → SNS/Lambda for real-time ingestion trigger (optional)
- Applies bucket policy to restrict access to `legal-rag-role` only

### OpenSearch Setup (`setup_opensearch.sh`)
- Creates an OpenSearch domain (t3.medium for dev, m6g.large for prod)
- Configures fine-grained access control
- Creates the legal documents index with the schema above
- Enables k-NN plugin

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Chunk size | 512 tokens, 64 overlap | Balances context richness vs. embedding noise |
| Dedup strategy | SHA-256 hash of chunk text | Exact-match dedup; fast, no false negatives |
| File tracking | ETag (MD5) from S3 | S3-native, no extra hashing needed |
| Re-ranking α | 0.7 (semantic) / 0.3 (keyword) | Legal text rewards exact term matches; blend preserves both |
| Top-K | 5 final (10 pre-rerank candidates) | Empirically good for legal Q&A |
| Citation format | file + page + section | Supports legal citation standards |

---

## Pending Decisions (Awaiting User Input)

- [ ] **Embedding model choice** — select from the 4 options listed above
- [ ] **LLM model choice** — select from the 4 options listed above
- [ ] **OpenSearch deployment size** — dev (t3.medium) or production scale
- [ ] **File tracking backend** — SQLite (dev/simple) or DynamoDB (production/scalable)
- [ ] **UI framework** — Streamlit (fast to build) or React (more polished)
- [ ] **Real-time ingestion** — S3 Event Notifications + Lambda, or scheduled polling

---

## Environment Variables (`config.env` — gitignored)

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
S3_BUCKET_NAME=legal-rag-documents
OPENSEARCH_ENDPOINT=
OPENSEARCH_INDEX=legal-docs
BEDROCK_EMBEDDING_MODEL_ID=          # e.g., amazon.titan-embed-text-v2:0
BEDROCK_LLM_MODEL_ID=                # e.g., claude-sonnet-4-6
CHUNK_SIZE=512
CHUNK_OVERLAP=64
TOP_K=5
RERANK_ALPHA=0.7
```

---

## Development Phases

1. **Phase 1 — Infrastructure**: IAM, S3, OpenSearch provisioning scripts
2. **Phase 2 — Ingestion Pipeline**: file watcher, extractor, chunker, embedder, middleware, OpenSearch write
3. **Phase 3 — Query Pipeline**: query embedder, hybrid search, re-ranker, LLM caller
4. **Phase 4 — UIs**: upload UI (Pipeline 1) + chat UI (Pipeline 2)
5. **Phase 5 — Integration & Testing**: end-to-end tests, dedup validation, citation accuracy checks

---

## Getting Started (After Approval)

```bash
# 1. Clone / enter project directory
cd legal-rag-aws

# 2. Configure AWS credentials
cp infra/config.env.example infra/config.env
# Fill in AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

# 3. Provision all AWS infrastructure
bash infra/setup_iam.sh
bash infra/setup_s3.sh
bash infra/setup_opensearch.sh

# 4. Install Python dependencies
pip install -r requirements.txt

# 5. Run ingestion pipeline
python pipeline1_ingestion/ingest_pipeline.py

# 6. Run chat UI
streamlit run pipeline2_query/ui/chat_app.py
```
