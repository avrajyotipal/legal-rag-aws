"""
Python equivalent of all shell setup scripts.
Run: python infra/setup_infra.py
Provisions IAM, S3, and OpenSearch, then creates the k-NN index.
"""
import io
import json
import re
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows so box/arrow chars don't crash cp1252
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import boto3
from dotenv import load_dotenv
import os

# ── Load config ────────────────────────────────────────────────────────────────
_HERE = Path(__file__).parent
load_dotenv(_HERE / "config.env")

REGION         = os.environ["AWS_REGION"]
ADMIN_KEY      = os.environ["AWS_ACCESS_KEY_ID"]
ADMIN_SECRET   = os.environ["AWS_SECRET_ACCESS_KEY"]
BUCKET         = os.environ["S3_BUCKET_NAME"]
DOMAIN         = os.environ["OPENSEARCH_DOMAIN_NAME"]
INDEX          = os.environ["OPENSEARCH_INDEX"]
EMBED_DIM      = int(os.getenv("BEDROCK_EMBEDDING_DIMENSIONS", "1024"))

POLICY_NAME    = "legal-rag-policy"
USER_NAME      = "legal-rag-svc"
CONFIG_PATH    = _HERE / "config.env"


def _session():
    return boto3.Session(
        aws_access_key_id=ADMIN_KEY,
        aws_secret_access_key=ADMIN_SECRET,
        region_name=REGION,
    )


def _update_config(key: str, value: str):
    text = CONFIG_PATH.read_text()
    pattern = rf"^{re.escape(key)}=.*$"
    replacement = f"{key}={value}"
    if re.search(pattern, text, re.MULTILINE):
        text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
    else:
        text += f"\n{key}={value}\n"
    CONFIG_PATH.write_text(text)


def step_iam():
    print("\n--- STEP 1/4: IAM ---")
    iam = _session().client("iam")
    sts = _session().client("sts")
    account_id = sts.get_caller_identity()["Account"]
    print(f"Account ID: {account_id}")

    policy_doc = json.dumps({
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "S3Access",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject", "s3:PutObject", "s3:DeleteObject",
                    "s3:ListBucket", "s3:HeadObject",
                    "s3:GetObjectTagging", "s3:PutObjectTagging"
                ],
                "Resource": [
                    f"arn:aws:s3:::{BUCKET}",
                    f"arn:aws:s3:::{BUCKET}/*"
                ]
            },
            {
                "Sid": "BedrockAccess",
                "Effect": "Allow",
                "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                "Resource": [
                    f"arn:aws:bedrock:{REGION}::foundation-model/amazon.titan-embed-text-v2:0",
                    f"arn:aws:bedrock:{REGION}::foundation-model/amazon.nova-pro-v1:0"
                ]
            },
            {
                "Sid": "OpenSearchAccess",
                "Effect": "Allow",
                "Action": "es:ESHttp*",
                "Resource": f"arn:aws:es:{REGION}:{account_id}:domain/{DOMAIN}/*"
            }
        ]
    })

    policy_arn = f"arn:aws:iam::{account_id}:policy/{POLICY_NAME}"

    # Try to create/update dedicated IAM user; fall back gracefully if no IAM admin perms
    try:
        try:
            iam.get_policy(PolicyArn=policy_arn)
            versions = iam.list_policy_versions(PolicyArn=policy_arn)["Versions"]
            for v in versions:
                if not v["IsDefaultVersion"]:
                    iam.delete_policy_version(PolicyArn=policy_arn, VersionId=v["VersionId"])
            iam.create_policy_version(PolicyArn=policy_arn, PolicyDocument=policy_doc, SetAsDefault=True)
            print(f"[IAM] Policy '{POLICY_NAME}' updated")
        except iam.exceptions.NoSuchEntityException:
            iam.create_policy(
                PolicyName=POLICY_NAME,
                PolicyDocument=policy_doc,
                Description="Legal RAG system service permissions"
            )
            print(f"[IAM] Policy '{POLICY_NAME}' created")

        try:
            iam.get_user(UserName=USER_NAME)
            print(f"[IAM] User '{USER_NAME}' already exists")
        except iam.exceptions.NoSuchEntityException:
            iam.create_user(UserName=USER_NAME, Tags=[{"Key": "Project", "Value": "legal-rag"}])
            print(f"[IAM] User '{USER_NAME}' created")

        iam.attach_user_policy(UserName=USER_NAME, PolicyArn=policy_arn)
        print(f"[IAM] Policy attached to '{USER_NAME}'")

        existing = iam.list_access_keys(UserName=USER_NAME)["AccessKeyMetadata"]
        for k in existing:
            iam.delete_access_key(UserName=USER_NAME, AccessKeyId=k["AccessKeyId"])
        new_key = iam.create_access_key(UserName=USER_NAME)["AccessKey"]
        _update_config("SVC_ACCESS_KEY_ID", new_key["AccessKeyId"])
        _update_config("SVC_SECRET_ACCESS_KEY", new_key["SecretAccessKey"])
        print(f"[IAM] Service key saved: {new_key['AccessKeyId']}")

    except Exception as e:
        print(f"[IAM] WARN: Cannot manage IAM (no admin perms): {e}")
        print(f"[IAM] Using provided admin credentials as service credentials.")
        _update_config("SVC_ACCESS_KEY_ID", ADMIN_KEY)
        _update_config("SVC_SECRET_ACCESS_KEY", ADMIN_SECRET)

    return account_id


def step_s3():
    print("\n--- STEP 2/4: S3 ---")
    s3 = _session().client("s3")

    bucket_exists = False
    try:
        s3.head_bucket(Bucket=BUCKET)
        bucket_exists = True
        print(f"[S3] Bucket '{BUCKET}' already exists")
    except s3.exceptions.NoSuchBucket:
        pass
    except Exception as e:
        code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchBucket"):
            pass  # bucket doesn't exist yet — create it
        elif code == "301":
            # bucket exists in a different region — still ours
            bucket_exists = True
            print(f"[S3] Bucket '{BUCKET}' exists (different region redirect)")
        else:
            raise

    if not bucket_exists:
        if REGION == "us-east-1":
            s3.create_bucket(Bucket=BUCKET)
        else:
            s3.create_bucket(
                Bucket=BUCKET,
                CreateBucketConfiguration={"LocationConstraint": REGION}
            )
        print(f"[S3] Bucket '{BUCKET}' created")

    s3.put_bucket_versioning(
        Bucket=BUCKET,
        VersioningConfiguration={"Status": "Enabled"}
    )
    s3.put_bucket_encryption(
        Bucket=BUCKET,
        ServerSideEncryptionConfiguration={
            "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}, "BucketKeyEnabled": True}]
        }
    )
    s3.put_public_access_block(
        Bucket=BUCKET,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True, "IgnorePublicAcls": True,
            "BlockPublicPolicy": True, "RestrictPublicBuckets": True
        }
    )
    print(f"[S3] Bucket configured: versioning=ON, encryption=AES-256, public=BLOCKED")


def step_opensearch(account_id: str) -> str:
    print("\n--- STEP 3/4: OpenSearch domain ---")
    os_client = _session().client("opensearch")

    access_policy = json.dumps({
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {
                "AWS": [
                    f"arn:aws:iam::{account_id}:user/{USER_NAME}",
                    f"arn:aws:iam::{account_id}:root"
                ]
            },
            "Action": "es:*",
            "Resource": f"arn:aws:es:{REGION}:{account_id}:domain/{DOMAIN}/*"
        }]
    })

    try:
        info = os_client.describe_domain(DomainName=DOMAIN)
        print(f"[OpenSearch] Domain '{DOMAIN}' already exists")
        endpoint = info["DomainStatus"].get("Endpoint", "")
    except os_client.exceptions.ResourceNotFoundException:
        print(f"[OpenSearch] Creating domain '{DOMAIN}' (t3.small.search, 20 GB gp3)…")
        os_client.create_domain(
            DomainName=DOMAIN,
            EngineVersion="OpenSearch_2.13",
            ClusterConfig={"InstanceType": "t3.small.search", "InstanceCount": 1,
                           "DedicatedMasterEnabled": False, "ZoneAwarenessEnabled": False},
            EBSOptions={"EBSEnabled": True, "VolumeType": "gp3", "VolumeSize": 20},
            AccessPolicies=access_policy,
            NodeToNodeEncryptionOptions={"Enabled": True},
            EncryptionAtRestOptions={"Enabled": True},
            DomainEndpointOptions={
                "EnforceHTTPS": True,
                "TLSSecurityPolicy": "Policy-Min-TLS-1-2-2019-07"
            },
            AdvancedSecurityOptions={"Enabled": False},
        )
        endpoint = ""

    # Poll until active
    print("[OpenSearch] Waiting for domain to become active (may take 10-15 min)…")
    for attempt in range(30):
        info = os_client.describe_domain(DomainName=DOMAIN)
        status = info["DomainStatus"]
        processing = status.get("Processing", True)
        endpoint = status.get("Endpoint", "")

        if not processing and endpoint:
            print(f"[OpenSearch] Domain is active. Endpoint: {endpoint}")
            break

        print(f"  Still processing… attempt {attempt+1}/30, waiting 60s")
        time.sleep(60)
    else:
        print("[ERROR] Timed out waiting for OpenSearch domain. Check AWS console.")
        sys.exit(1)

    full_endpoint = f"https://{endpoint}"
    _update_config("OPENSEARCH_ENDPOINT", full_endpoint)
    print(f"[OpenSearch] Endpoint saved to config.env")
    return full_endpoint


def step_create_index(endpoint: str):
    print("\n--- STEP 4/4: OpenSearch index ---")
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from requests_aws4auth import AWS4Auth

    # Re-load config to pick up newly written SVC credentials
    load_dotenv(_HERE / "config.env", override=True)
    svc_key    = os.environ.get("SVC_ACCESS_KEY_ID") or ADMIN_KEY
    svc_secret = os.environ.get("SVC_SECRET_ACCESS_KEY") or ADMIN_SECRET

    auth = AWS4Auth(svc_key, svc_secret, REGION, "es")
    host = endpoint.replace("https://", "").rstrip("/")

    client = OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
    )

    if client.indices.exists(index=INDEX):
        print(f"[Index] '{INDEX}' already exists — skipping.")
        return

    index_body = {
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
                "chunk_text":         {"type": "text", "analyzer": "english",
                                       "fields": {"keyword": {"type": "keyword", "ignore_above": 512}}},
                "embedding":          {"type": "knn_vector", "dimension": EMBED_DIM,
                                       "method": {"name": "hnsw", "space_type": "cosinesimil",
                                                  "engine": "nmslib",
                                                  "parameters": {"ef_construction": 512, "m": 16}}},
                "content_hash":       {"type": "keyword"},
                "file_hash":          {"type": "keyword"},
                "source_file":        {"type": "keyword"},
                "s3_key":             {"type": "keyword"},
                "page_number":        {"type": "integer"},
                "section_heading":    {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                "chunk_index":        {"type": "integer"},
                "uploader":           {"type": "keyword"},
                "ingestion_timestamp":{"type": "date"},
            }
        }
    }
    resp = client.indices.create(index=INDEX, body=index_body)
    print(f"[Index] '{INDEX}' created: {resp}")


if __name__ == "__main__":
    print("=" * 60)
    print("  Legal RAG — AWS Infrastructure Setup (Python)")
    print(f"  Region: {REGION} | Bucket: {BUCKET} | Domain: {DOMAIN}")
    print("=" * 60)

    account_id = step_iam()
    step_s3()
    endpoint   = step_opensearch(account_id)
    step_create_index(endpoint)

    print("\n" + "=" * 60)
    print("  All infrastructure ready!")
    print("  Next: python sample_docs/create_docs.py")
    print("        python pipeline1_ingestion/ingest_pipeline.py")
    print("=" * 60)
