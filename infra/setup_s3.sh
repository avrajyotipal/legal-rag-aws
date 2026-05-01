#!/usr/bin/env bash
# Creates and configures the S3 bucket for legal document storage.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

echo "=== [S3] Setting up bucket: $S3_BUCKET_NAME ==="

ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text --region "$AWS_REGION")

# ── Create bucket ─────────────────────────────────────────────────────────────
if aws s3api head-bucket --bucket "$S3_BUCKET_NAME" --region "$AWS_REGION" 2>/dev/null; then
  echo "[S3] Bucket '$S3_BUCKET_NAME' already exists"
else
  echo "[S3] Creating bucket '$S3_BUCKET_NAME'"
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket \
      --bucket "$S3_BUCKET_NAME" \
      --region "$AWS_REGION"
  else
    aws s3api create-bucket \
      --bucket "$S3_BUCKET_NAME" \
      --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION"
  fi
fi

# ── Enable versioning ─────────────────────────────────────────────────────────
echo "[S3] Enabling versioning"
aws s3api put-bucket-versioning \
  --bucket "$S3_BUCKET_NAME" \
  --versioning-configuration Status=Enabled \
  --region "$AWS_REGION"

# ── Enable server-side encryption (AES-256) ───────────────────────────────────
echo "[S3] Enabling server-side encryption"
aws s3api put-bucket-encryption \
  --bucket "$S3_BUCKET_NAME" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      },
      "BucketKeyEnabled": true
    }]
  }' \
  --region "$AWS_REGION"

# ── Block all public access ────────────────────────────────────────────────────
echo "[S3] Blocking public access"
aws s3api put-public-access-block \
  --bucket "$S3_BUCKET_NAME" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true \
  --region "$AWS_REGION"

# ── Bucket policy: restrict to service user and admin ─────────────────────────
echo "[S3] Applying bucket policy"
BUCKET_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowServiceUser",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::${ACCOUNT_ID}:user/legal-rag-svc"
      },
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket",
        "s3:HeadObject",
        "s3:GetObjectTagging",
        "s3:PutObjectTagging"
      ],
      "Resource": [
        "arn:aws:s3:::${S3_BUCKET_NAME}",
        "arn:aws:s3:::${S3_BUCKET_NAME}/*"
      ]
    }
  ]
}
EOF
)
aws s3api put-bucket-policy \
  --bucket "$S3_BUCKET_NAME" \
  --policy "$BUCKET_POLICY" \
  --region "$AWS_REGION"

echo ""
echo "[S3] Done. Bucket '$S3_BUCKET_NAME' configured."
echo "      Versioning: ON | Encryption: AES-256 | Public access: BLOCKED"
