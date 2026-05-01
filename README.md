# Legal RAG System on AWS

A production-grade Retrieval-Augmented Generation (RAG) system for legal teams, built entirely on AWS. Upload PDF and DOCX case documents, then ask natural-language questions and receive grounded answers with source citations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Pipeline 1 — Document Ingestion            │
│                                                             │
│  Upload UI  →  S3  →  ETag file tracker (SQLite)            │
│               →  Text extractor (pdfplumber / python-docx)  │
│               →  Chunker (512 tokens, 64 overlap, tiktoken) │
│               →  Titan Embeddings V2 (Bedrock, 1024-dim)    │
│               →  SHA-256 dedup check                        │
│               →  OpenSearch (kNN + BM25 index)              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                  Pipeline 2 — Chat / Query                  │
│                                                             │
│  Chat UI  →  Titan Embeddings V2 (query vector)             │
│           →  OpenSearch hybrid search (kNN + BM25)          │
│           →  Custom re-ranker (α=0.7 semantic, 0.3 keyword) │
│           →  Amazon Nova Pro (Bedrock LLM)                  │
│           →  Answer with inline citations                    │
└─────────────────────────────────────────────────────────────┘
```

---

## AWS Services

| Service | Purpose |
|---|---|
| **S3** | Primary document store (PDF/DOCX files) |
| **Bedrock — Titan Embeddings V2** | 1024-dim dense vectors for documents and queries |
| **Bedrock — Amazon Nova Pro** | LLM for grounded answer generation |
| **OpenSearch Service** | Vector (kNN/HNSW) + BM25 keyword search index |
| **IAM** | Scoped service account (`legal-rag-svc`) |

---

## Project Structure

```
legal-rag-aws/
├── app.py                           # Unified Streamlit UI (upload + chat)
├── requirements.txt
├── infra/
│   ├── setup_infra.py               # Provisions IAM, S3, OpenSearch via boto3
│   └── config.env                  # AWS config and credentials (gitignored)
├── pipeline1_ingestion/
│   ├── file_watcher.py              # S3 ETag-based new-file detector (SQLite)
│   ├── extractor.py                 # PDF + DOCX text extraction
│   ├── chunker.py                   # Overlapping token-based chunking
│   ├── embedder.py                  # Bedrock embedding calls
│   ├── middleware.py                # Dedup + OpenSearch write layer
│   └── ingest_pipeline.py           # Orchestrator
├── pipeline2_query/
│   ├── query_embedder.py            # Embed user query
│   ├── searcher.py                  # Hybrid search (kNN + BM25)
│   ├── reranker.py                  # Score blending and re-ranking
│   ├── llm_caller.py                # Bedrock LLM with citation prompt
│   └── query_pipeline.py            # Orchestrator
└── shared/
    ├── aws_clients.py               # Boto3 client factory
    ├── config.py                    # Loads config.env
    └── logger.py                    # UTF-8 safe structured logging
```

---

## Prerequisites

- Python 3.10+
- AWS account with Bedrock model access enabled for:
  - `amazon.titan-embed-text-v2:0`
  - `amazon.nova-pro-v1:0`
- IAM user with AdministratorAccess (for initial setup only)

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-username/legal-rag-aws.git
cd legal-rag-aws
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp infra/config.env.example infra/config.env
```

Edit `infra/config.env` and fill in:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=<your-admin-key-id>
AWS_SECRET_ACCESS_KEY=<your-admin-secret>
```

### 3. Provision AWS infrastructure

This creates the IAM service user, S3 bucket, and OpenSearch domain automatically — no AWS Console steps required.

```bash
python infra/setup_infra.py
```

The script populates the remaining fields in `config.env` (OpenSearch endpoint, service account keys, resource names).

> **Note:** OpenSearch domain creation takes 10–15 minutes. The script polls until the domain is active.

### 4. Launch the app

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Usage

### Uploading Documents

1. Go to the **Upload Documents** tab.
2. Enter your name / team.
3. Select one or more PDF or DOCX files.
4. Click **Upload to S3**.
5. Click **Index new uploads** to run the ingestion pipeline and make documents searchable.

### Asking Questions

1. Go to the **Chat** tab.
2. Type a legal question in the input box.
3. The system retrieves the most relevant passages from your indexed documents and generates a grounded answer with source citations (file name, page number, section).

---

## Configuration

All parameters live in `infra/config.env`:

| Variable | Default | Description |
|---|---|---|
| `CHUNK_SIZE` | `512` | Tokens per chunk (tiktoken cl100k_base) |
| `CHUNK_OVERLAP` | `64` | Overlap between consecutive chunks |
| `TOP_K` | `5` | Final chunks passed to the LLM |
| `PRE_RERANK_K` | `10` | Candidates retrieved before re-ranking |
| `RERANK_ALPHA` | `0.7` | Weight of semantic score vs. keyword score |
| `BEDROCK_EMBEDDING_MODEL_ID` | `amazon.titan-embed-text-v2:0` | Embedding model |
| `BEDROCK_LLM_MODEL_ID` | `amazon.nova-pro-v1:0` | Answer generation model |

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Chunk size | 512 tokens, 64 overlap | Balances context richness vs. embedding noise |
| Dedup strategy | SHA-256 hash of chunk text | Exact-match dedup; fast, no false negatives |
| File tracking | S3 ETag (MD5) via SQLite | S3-native; prevents reprocessing unchanged files |
| Re-ranking blend | α=0.7 semantic + 0.3 keyword | Legal text rewards exact term matches |
| Embedding dimensions | 1024 | Titan V2 native; HNSW cosine similarity index |

---

## Running the Ingestion Pipeline Standalone

To process new S3 uploads without the UI:

```bash
python pipeline1_ingestion/ingest_pipeline.py
```

Exit code `0` = all files processed successfully. Exit code `1` = one or more failures.

---

## License

MIT
