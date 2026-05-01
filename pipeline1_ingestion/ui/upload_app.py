"""
Streamlit upload UI for Pipeline 1.
Legal team members use this to upload PDF/DOCX files to S3.
Run: streamlit run pipeline1_ingestion/ui/upload_app.py
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.aws_clients import get_s3_client
from shared.config import S3_BUCKET_NAME
from shared.logger import get_logger

logger = get_logger("upload_ui")

st.set_page_config(
    page_title="Legal Document Upload",
    page_icon="⚖",
    layout="centered",
)

st.title("Legal Document Upload")
st.caption(f"Destination bucket: `{S3_BUCKET_NAME}`")
st.markdown("---")

uploader_name = st.text_input(
    "Your name / team",
    placeholder="e.g., Legal Team — Jane Smith",
)

uploaded_files = st.file_uploader(
    "Select PDF or DOCX documents",
    type=["pdf", "docx", "doc"],
    accept_multiple_files=True,
)

upload_btn = st.button(
    "Upload to S3",
    disabled=(not uploaded_files or not uploader_name.strip()),
    type="primary",
)

if upload_btn:
    s3 = get_s3_client()
    ts = datetime.now(timezone.utc).isoformat()
    results = []

    for f in uploaded_files:
        unique_key = f"uploads/{uuid.uuid4()}_{f.name}"
        content_type = (
            "application/pdf"
            if f.name.lower().endswith(".pdf")
            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        tags = f"uploader={uploader_name.strip()}&upload_timestamp={ts}"

        try:
            s3.put_object(
                Bucket=S3_BUCKET_NAME,
                Key=unique_key,
                Body=f.read(),
                ContentType=content_type,
                Tagging=tags,
            )
            results.append(("ok", f.name, unique_key))
            logger.info(f"Uploaded {f.name} → s3://{S3_BUCKET_NAME}/{unique_key}")
        except Exception as exc:
            results.append(("err", f.name, str(exc)))
            logger.error(f"Upload failed for {f.name}: {exc}")

    st.markdown("### Upload Results")
    for status, name, detail in results:
        if status == "ok":
            st.success(f"{name}  →  `{detail}`")
        else:
            st.error(f"{name}  →  {detail}")

    if any(r[0] == "ok" for r in results):
        st.info(
            "Files uploaded successfully. "
            "Run `python pipeline1_ingestion/ingest_pipeline.py` to index them."
        )

st.markdown("---")
st.markdown("### Previously Uploaded Files")

try:
    s3 = get_s3_client()
    resp = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="uploads/", MaxKeys=50)
    objects = resp.get("Contents", [])
    if objects:
        rows = [
            {"File": obj["Key"].split("/", 1)[-1], "Size (KB)": round(obj["Size"] / 1024, 1),
             "Last Modified": obj["LastModified"].strftime("%Y-%m-%d %H:%M UTC")}
            for obj in sorted(objects, key=lambda x: x["LastModified"], reverse=True)
        ]
        st.dataframe(rows, width="stretch")
    else:
        st.caption("No files uploaded yet.")
except Exception as exc:
    st.warning(f"Could not list S3 files: {exc}")
