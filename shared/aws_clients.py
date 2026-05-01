import boto3
from shared.config import AWS_REGION, SVC_ACCESS_KEY_ID, SVC_SECRET_ACCESS_KEY, OPENSEARCH_ENDPOINT


def _session() -> boto3.Session:
    return boto3.Session(
        aws_access_key_id=SVC_ACCESS_KEY_ID,
        aws_secret_access_key=SVC_SECRET_ACCESS_KEY,
        region_name=AWS_REGION,
    )


def get_s3_client():
    return _session().client("s3")


def get_bedrock_client():
    return _session().client("bedrock-runtime", region_name=AWS_REGION)


def get_opensearch_client():
    from opensearchpy import OpenSearch, RequestsHttpConnection
    from requests_aws4auth import AWS4Auth

    # Use explicit credentials directly — avoids boto3 version differences
    auth = AWS4Auth(SVC_ACCESS_KEY_ID, SVC_SECRET_ACCESS_KEY, AWS_REGION, "es")
    host = OPENSEARCH_ENDPOINT.replace("https://", "").replace("http://", "").rstrip("/")
    return OpenSearch(
        hosts=[{"host": host, "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        timeout=60,
    )
