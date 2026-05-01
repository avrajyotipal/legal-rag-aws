"""
Unified Legal RAG UI — upload documents and query them from a single interface.
Run: streamlit run app.py
"""
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from shared.aws_clients import get_s3_client, get_opensearch_client
from shared.config import S3_BUCKET_NAME, OPENSEARCH_INDEX
from shared.logger import get_logger
from pipeline2_query.query_pipeline import run_query
from pipeline1_ingestion.ingest_pipeline import run_ingestion

logger = get_logger("app")

st.set_page_config(
    page_title="Legal Research Assistant",
    page_icon="⚖",
    layout="wide",
)

# ── Header ────────────────────────────────────────────────────────────────────
st.title("Legal Research Assistant")
st.caption("Upload legal documents and ask questions grounded in your case files.")
st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_chat, tab_upload = st.tabs(["Chat", "Upload Documents"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — CHAT
# ══════════════════════════════════════════════════════════════════════════════
def _render_citations(citations: list[dict]) -> None:
    with st.expander(f"Sources ({len(citations)})"):
        for cit in citations:
            line = f"**[Source {cit['index']}]** `{cit['source_file']}`"
            if cit.get("page"):
                line += f" — Page {cit['page']}"
            if cit.get("section"):
                line += f" | {cit['section']}"
            if cit.get("score"):
                line += f" *(relevance: {cit['score']:.2%})*"
            st.markdown(line)


with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    col_chat, col_info = st.columns([3, 1])

    with col_info:
        st.markdown("**Knowledge Base**")
        try:
            os_client = get_opensearch_client()
            stats = os_client.count(index=OPENSEARCH_INDEX)
            doc_count = stats.get("count", 0)
            st.metric("Indexed chunks", doc_count)
        except Exception:
            st.caption("(stats unavailable)")

        if st.button("Clear conversation", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

    with col_chat:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("citations"):
                    _render_citations(msg["citations"])

        if prompt := st.chat_input("Ask a legal question..."):
            with st.chat_message("user"):
                st.markdown(prompt)
            st.session_state.messages.append({"role": "user", "content": prompt})

            with st.chat_message("assistant"):
                with st.spinner("Searching documents and generating answer..."):
                    result = run_query(prompt)

                st.markdown(result["answer"])
                if result.get("citations"):
                    _render_citations(result["citations"])

            st.session_state.messages.append({
                "role":      "assistant",
                "content":   result["answer"],
                "citations": result.get("citations", []),
            })


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — UPLOAD DOCUMENTS
# ══════════════════════════════════════════════════════════════════════════════
with tab_upload:
    st.markdown("### Upload New Documents")
    st.caption(f"Files are stored in S3 bucket: `{S3_BUCKET_NAME}`")

    uploader_name = st.text_input(
        "Your name / team",
        placeholder="e.g., Legal Team — Jane Smith",
        key="uploader_name",
    )

    uploaded_files = st.file_uploader(
        "Select PDF or DOCX documents",
        type=["pdf", "docx", "doc"],
        accept_multiple_files=True,
        key="file_uploader",
    )

    col_upload, col_index = st.columns(2)

    with col_upload:
        upload_btn = st.button(
            "Upload to S3",
            disabled=(not uploaded_files or not uploader_name.strip()),
            type="primary",
            use_container_width=True,
        )

    with col_index:
        index_btn = st.button(
            "Index new uploads",
            type="secondary",
            use_container_width=True,
            help="Process all unindexed S3 files through the ingestion pipeline.",
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
                logger.info(f"Uploaded {f.name} to s3://{S3_BUCKET_NAME}/{unique_key}")
            except Exception as exc:
                results.append(("err", f.name, str(exc)))
                logger.error(f"Upload failed for {f.name}: {exc}")

        st.markdown("#### Upload Results")
        for status, name, detail in results:
            if status == "ok":
                st.success(f"{name}  →  `{detail}`")
            else:
                st.error(f"{name}  →  {detail}")

        if any(r[0] == "ok" for r in results):
            st.info('Files uploaded. Click "Index new uploads" to make them searchable.')

    if index_btn:
        with st.spinner("Running ingestion pipeline..."):
            try:
                result = run_ingestion()
                if result["processed"] == 0 and result["failed"] == 0:
                    st.info("No new files to index. All uploads are already indexed.")
                elif result["failed"] == 0:
                    st.success(
                        f"Indexed {result['processed']} file(s) successfully. "
                        "New documents are now searchable in the Chat tab."
                    )
                else:
                    st.warning(
                        f"Processed {result['processed']} file(s), "
                        f"failed {result['failed']}. Check logs for details."
                    )
            except Exception as exc:
                st.error(f"Ingestion error: {exc}")
                logger.error(f"Ingestion error from UI: {exc}", exc_info=True)

    st.markdown("---")
    st.markdown("### Previously Uploaded Files")

    try:
        s3 = get_s3_client()
        resp = s3.list_objects_v2(Bucket=S3_BUCKET_NAME, Prefix="uploads/", MaxKeys=100)
        objects = resp.get("Contents", [])
        if objects:
            rows = [
                {
                    "File": obj["Key"].split("/", 1)[-1],
                    "Size (KB)": round(obj["Size"] / 1024, 1),
                    "Last Modified": obj["LastModified"].strftime("%Y-%m-%d %H:%M UTC"),
                }
                for obj in sorted(objects, key=lambda x: x["LastModified"], reverse=True)
            ]
            st.dataframe(rows, width="stretch")
        else:
            st.caption("No files uploaded yet.")
    except Exception as exc:
        st.warning(f"Could not list S3 files: {exc}")
