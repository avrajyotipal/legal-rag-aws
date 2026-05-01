#!/usr/bin/env bash
# Provisions an AWS OpenSearch Service domain and saves the endpoint to config.env.
# Domain creation takes 10-15 minutes. Script waits and polls until active.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/config.env"

DOMAIN="$OPENSEARCH_DOMAIN_NAME"
echo "=== [OpenSearch] Setting up domain: $DOMAIN ==="

ACCOUNT_ID=$(aws sts get-caller-identity \
  --query Account --output text --region "$AWS_REGION")

# ── Build access policy (IAM-based, no VPC required) ─────────────────────────
ACCESS_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::${ACCOUNT_ID}:user/legal-rag-svc",
          "arn:aws:iam::${ACCOUNT_ID}:root"
        ]
      },
      "Action": "es:*",
      "Resource": "arn:aws:es:${AWS_REGION}:${ACCOUNT_ID}:domain/${DOMAIN}/*"
    }
  ]
}
EOF
)

# ── Check if domain exists ────────────────────────────────────────────────────
DOMAIN_EXISTS=$(aws opensearch describe-domain \
  --domain-name "$DOMAIN" \
  --region "$AWS_REGION" \
  --query 'DomainStatus.DomainName' \
  --output text 2>/dev/null || echo "NONE")

if [ "$DOMAIN_EXISTS" = "$DOMAIN" ]; then
  echo "[OpenSearch] Domain '$DOMAIN' already exists — skipping creation"
else
  echo "[OpenSearch] Creating domain '$DOMAIN' (t3.small.search, 20 GB gp3)"
  aws opensearch create-domain \
    --domain-name "$DOMAIN" \
    --engine-version "OpenSearch_2.13" \
    --cluster-config "InstanceType=t3.small.search,InstanceCount=1,DedicatedMasterEnabled=false,ZoneAwarenessEnabled=false" \
    --ebs-options "EBSEnabled=true,VolumeType=gp3,VolumeSize=20" \
    --access-policies "$ACCESS_POLICY" \
    --node-to-node-encryption-options "Enabled=true" \
    --encryption-at-rest-options "Enabled=true" \
    --domain-endpoint-options "EnforceHTTPS=true,TLSSecurityPolicy=Policy-Min-TLS-1-2-2019-07" \
    --advanced-security-options "Enabled=false" \
    --region "$AWS_REGION"
  echo "[OpenSearch] Domain creation started. Waiting for active state..."
fi

# ── Poll until domain is active ───────────────────────────────────────────────
echo "[OpenSearch] Polling domain status (this may take 10-15 minutes)..."
while true; do
  STATUS=$(aws opensearch describe-domain \
    --domain-name "$DOMAIN" \
    --region "$AWS_REGION" \
    --query 'DomainStatus.Processing' \
    --output text)

  if [ "$STATUS" = "False" ]; then
    echo "[OpenSearch] Domain is active."
    break
  fi
  echo "  Still processing... waiting 60 seconds"
  sleep 60
done

# ── Fetch and save endpoint ───────────────────────────────────────────────────
ENDPOINT=$(aws opensearch describe-domain \
  --domain-name "$DOMAIN" \
  --region "$AWS_REGION" \
  --query 'DomainStatus.Endpoint' \
  --output text)

if [ -z "$ENDPOINT" ] || [ "$ENDPOINT" = "None" ]; then
  echo "[ERROR] Could not retrieve endpoint. Check domain status in AWS Console."
  exit 1
fi

ENDPOINT_HTTPS="https://${ENDPOINT}"
echo "[OpenSearch] Endpoint: $ENDPOINT_HTTPS"

# ── Write endpoint into config.env ────────────────────────────────────────────
CONFIG_FILE="$SCRIPT_DIR/config.env"
python3 - <<PYEOF
import re, pathlib

path = pathlib.Path("$CONFIG_FILE")
text = path.read_text()
pattern = r'^OPENSEARCH_ENDPOINT=.*$'
replacement = 'OPENSEARCH_ENDPOINT=$ENDPOINT_HTTPS'
if re.search(pattern, text, re.MULTILINE):
    text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
else:
    text += '\nOPENSEARCH_ENDPOINT=$ENDPOINT_HTTPS\n'
path.write_text(text)
print("[OpenSearch] Endpoint saved to config.env")
PYEOF

echo ""
echo "[OpenSearch] Done."
echo "      Next step: python infra/create_opensearch_index.py"
