"""
Detects new, unprocessed files in S3 using a local SQLite registry keyed by S3 ETags.
Only PDF, DOCX, and DOC files are considered. Already-processed files are skipped.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from shared.aws_clients import get_s3_client
from shared.config import S3_BUCKET_NAME
from shared.logger import get_logger

logger = get_logger(__name__)
_DB_PATH = Path(__file__).parent / "file_tracker.db"
_SUPPORTED = {".pdf", ".docx", ".doc"}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH)
    c.execute("""
        CREATE TABLE IF NOT EXISTS processed_files (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            s3_key       TEXT    NOT NULL,
            etag         TEXT    NOT NULL UNIQUE,
            status       TEXT    NOT NULL DEFAULT 'processing',
            processed_at TEXT,
            created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    c.commit()
    return c


def _is_done(etag: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT status FROM processed_files WHERE etag = ?", (etag,)
        ).fetchone()
    return row is not None and row[0] == "done"


def _mark_processing(s3_key: str, etag: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO processed_files (s3_key, etag, status) VALUES (?, ?, 'processing')",
            (s3_key, etag),
        )


def mark_done(s3_key: str, etag: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE processed_files SET status='done', processed_at=? WHERE etag=?",
            (datetime.utcnow().isoformat(), etag),
        )


def mark_failed(etag: str) -> None:
    with _conn() as c:
        c.execute(
            "UPDATE processed_files SET status='failed', processed_at=? WHERE etag=?",
            (datetime.utcnow().isoformat(), etag),
        )


def get_new_files() -> list[dict]:
    """Returns metadata dicts for all S3 objects not yet successfully processed."""
    s3 = get_s3_client()
    new_files: list[dict] = []

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET_NAME):
        for obj in page.get("Contents", []):
            key: str = obj["Key"]
            if Path(key).suffix.lower() not in _SUPPORTED:
                continue

            etag = obj["ETag"].strip('"')
            if _is_done(etag):
                logger.debug(f"Already processed — skipping: {key}")
                continue

            _mark_processing(key, etag)
            new_files.append({
                "s3_key": key,
                "etag": etag,
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            })
            logger.info(f"Queued for processing: {key}  (etag={etag[:8]}...)")

    logger.info(f"Found {len(new_files)} new file(s) to process.")
    return new_files
