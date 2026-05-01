#!/usr/bin/env bash
# Provisions IAM policy, user, and access keys for the legal-rag service account.
# Run once with admin credentials. Writes SVC credentials back to config.env.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

POLICY_NAME="legal-rag-policy"
USER_NAME="legal-rag-svc"

echo "=== [IAM] Setting up service account ==="

# ── Get AWS account ID ────────────────────────────────────────────────────────
ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text \
  --region "$AWS_REGION")
echo "Account ID: $ACCOUNT_ID"

# ── Create IAM policy document ────────────────────────────────────────────────
POLICY_DOC=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3Access",
      "Effect": "Allow",
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
    },
    {
      "Sid": "BedrockAccess",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:${AWS_REGION}::foundation-model/amazon.titan-embed-text-v2:0",
        "arn:aws:bedrock:${AWS_REGION}::foundation-model/amazon.nova-pro-v1:0"
      ]
    },
    {
      "Sid": "OpenSearchAccess",
      "Effect": "Allow",
      "Action": "es:ESHttp*",
      "Resource": "arn:aws:es:${AWS_REGION}:${ACCOUNT_ID}:domain/${OPENSEARCH_DOMAIN_NAME}/*"
    }
  ]
}
EOF
)

# ── Create or update managed policy ──────────────────────────────────────────
POLICY_ARN="arn:aws:iam::${ACCOUNT_ID}:policy/${POLICY_NAME}"

if aws iam get-policy --policy-arn "$POLICY_ARN" --region "$AWS_REGION" &>/dev/null; then
  echo "[IAM] Policy '$POLICY_NAME' already exists — creating new version"
  aws iam create-policy-version \
    --policy-arn "$POLICY_ARN" \
    --policy-document "$POLICY_DOC" \
    --set-as-default \
    --region "$AWS_REGION"
else
  echo "[IAM] Creating policy '$POLICY_NAME'"
  aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document "$POLICY_DOC" \
    --description "Legal RAG system service permissions" \
    --region "$AWS_REGION"
fi

# ── Create IAM user ───────────────────────────────────────────────────────────
if aws iam get-user --user-name "$USER_NAME" --region "$AWS_REGION" &>/dev/null; then
  echo "[IAM] User '$USER_NAME' already exists"
else
  echo "[IAM] Creating user '$USER_NAME'"
  aws iam create-user \
    --user-name "$USER_NAME" \
    --tags Key=Project,Value=legal-rag \
    --region "$AWS_REGION"
fi

# ── Attach policy to user ─────────────────────────────────────────────────────
aws iam attach-user-policy \
  --user-name "$USER_NAME" \
  --policy-arn "$POLICY_ARN" \
  --region "$AWS_REGION"
echo "[IAM] Policy attached to '$USER_NAME'"

# ── Create access keys ────────────────────────────────────────────────────────
# Delete any existing keys first (max 2 allowed)
EXISTING_KEYS=$(aws iam list-access-keys \
  --user-name "$USER_NAME" \
  --query 'AccessKeyMetadata[*].AccessKeyId' \
  --output text --region "$AWS_REGION")
for KEY_ID in $EXISTING_KEYS; do
  echo "[IAM] Deleting old access key: $KEY_ID"
  aws iam delete-access-key --user-name "$USER_NAME" --access-key-id "$KEY_ID" --region "$AWS_REGION"
done

echo "[IAM] Creating new access keys for '$USER_NAME'"
KEY_OUTPUT=$(aws iam create-access-key \
  --user-name "$USER_NAME" \
  --region "$AWS_REGION" \
  --output json)

SVC_KEY_ID=$(echo "$KEY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['AccessKeyId'])")
SVC_SECRET=$(echo "$KEY_OUTPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['SecretAccessKey'])")

# ── Write SVC credentials into config.env ────────────────────────────────────
CONFIG_FILE="$SCRIPT_DIR/config.env"
python3 - <<PYEOF
import re, pathlib

path = pathlib.Path("$CONFIG_FILE")
text = path.read_text()

def set_var(text, key, value):
    pattern = rf'^{key}=.*$'
    replacement = f'{key}={value}'
    if re.search(pattern, text, re.MULTILINE):
        return re.sub(pattern, replacement, text, flags=re.MULTILINE)
    return text + f'\n{key}={value}\n'

text = set_var(text, 'SVC_ACCESS_KEY_ID', '$SVC_KEY_ID')
text = set_var(text, 'SVC_SECRET_ACCESS_KEY', '$SVC_SECRET')
path.write_text(text)
print("[IAM] SVC credentials written to config.env")
PYEOF

echo ""
echo "[IAM] Done. Service user '$USER_NAME' is ready."
echo "      SVC_ACCESS_KEY_ID and SVC_SECRET_ACCESS_KEY saved to config.env"
