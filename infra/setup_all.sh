#!/usr/bin/env bash
# Master setup script. Runs all infrastructure provisioning steps in order.
# Usage: bash infra/setup_all.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "============================================================"
echo "  Legal RAG — Full AWS Infrastructure Setup"
echo "============================================================"
echo ""

# Step 1 — IAM
echo "── STEP 1/4: IAM ───────────────────────────────────────────"
bash "$SCRIPT_DIR/setup_iam.sh"
echo ""

# Step 2 — S3
echo "── STEP 2/4: S3 ────────────────────────────────────────────"
bash "$SCRIPT_DIR/setup_s3.sh"
echo ""

# Step 3 — OpenSearch domain (slow: 10-15 min)
echo "── STEP 3/4: OpenSearch domain ─────────────────────────────"
bash "$SCRIPT_DIR/setup_opensearch.sh"
echo ""

# Step 4 — OpenSearch index
echo "── STEP 4/4: OpenSearch index ──────────────────────────────"
python3 "$SCRIPT_DIR/create_opensearch_index.py"
echo ""

echo "============================================================"
echo "  All infrastructure is ready. Next steps:"
echo ""
echo "  Install Python deps:   pip install -r requirements.txt"
echo "  Run ingestion UI:      streamlit run pipeline1_ingestion/ui/upload_app.py"
echo "  Run ingestion script:  python pipeline1_ingestion/ingest_pipeline.py"
echo "  Run chat UI:           streamlit run pipeline2_query/ui/chat_app.py"
echo "============================================================"
