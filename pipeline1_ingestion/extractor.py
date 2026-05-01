"""
Downloads a file from S3 and extracts structured text with page/section metadata.
Supports PDF (via pdfplumber) and DOCX (via python-docx).
"""
import io
from pathlib import Path

from shared.aws_clients import get_s3_client
from shared.config import S3_BUCKET_NAME
from shared.logger import get_logger

logger = get_logger(__name__)


def extract_from_s3(s3_key: str) -> list[dict]:
    """
    Returns a list of page dicts:
      { text, page_number, section_heading, uploader, upload_timestamp }
    """
    s3 = get_s3_client()
    obj = s3.get_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
    file_bytes = obj["Body"].read()
    tags = _get_tags(s3, s3_key)

    ext = Path(s3_key).suffix.lower()
    if ext == ".pdf":
        pages = _extract_pdf(file_bytes)
    elif ext in {".docx", ".doc"}:
        pages = _extract_docx(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

    for page in pages:
        page["uploader"] = tags.get("uploader", "unknown")
        page["upload_timestamp"] = tags.get("upload_timestamp", "")

    logger.info(f"Extracted {len(pages)} page segment(s) from {s3_key}")
    return pages


def _get_tags(s3_client, s3_key: str) -> dict:
    try:
        resp = s3_client.get_object_tagging(Bucket=S3_BUCKET_NAME, Key=s3_key)
        return {tag["Key"]: tag["Value"] for tag in resp.get("TagSet", [])}
    except Exception:
        return {}


def _extract_pdf(file_bytes: bytes) -> list[dict]:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                pages.append({
                    "text": text,
                    "page_number": i,
                    "section_heading": "",
                })
    return pages


def _extract_docx(file_bytes: bytes) -> list[dict]:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    pages: list[dict] = []
    current_heading = ""
    current_text: list[str] = []

    def _flush(heading: str, lines: list[str], page_num: int):
        combined = "\n".join(lines).strip()
        if combined:
            pages.append({
                "text": combined,
                "page_number": page_num,
                "section_heading": heading,
            })

    for para in doc.paragraphs:
        style = para.style.name or ""
        if style.startswith("Heading"):
            _flush(current_heading, current_text, len(pages) + 1)
            current_text = []
            current_heading = para.text.strip()
        else:
            stripped = para.text.strip()
            if stripped:
                current_text.append(stripped)

    _flush(current_heading, current_text, len(pages) + 1)
    return pages
