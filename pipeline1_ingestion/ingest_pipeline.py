"""
Pipeline 1 orchestrator — run this script to process all new documents.
Detects new S3 files → extracts text → chunks → embeds → stores in OpenSearch.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline1_ingestion.file_watcher import get_new_files, mark_done, mark_failed
from pipeline1_ingestion.extractor import extract_from_s3
from pipeline1_ingestion.chunker import chunk_pages
from pipeline1_ingestion.embedder import embed_chunks
from pipeline1_ingestion.middleware import store_chunks
from shared.logger import get_logger

logger = get_logger("ingest_pipeline")


def run_ingestion() -> dict:
    logger.info("=== Ingestion pipeline started ===")
    new_files = get_new_files()

    if not new_files:
        logger.info("No new files to process. Exiting.")
        return {"processed": 0, "failed": 0}

    processed = 0
    failed = 0

    for file_info in new_files:
        s3_key = file_info["s3_key"]
        etag = file_info["etag"]
        logger.info(f"Processing: {s3_key}")

        try:
            pages = extract_from_s3(s3_key)
            if not pages:
                logger.warning(f"No text content found in {s3_key} — marking done")
                mark_done(s3_key, etag)
                processed += 1
                continue

            chunks = chunk_pages(pages, s3_key, etag)
            chunks = embed_chunks(chunks)
            result = store_chunks(chunks)

            mark_done(s3_key, etag)
            logger.info(
                f"Finished {s3_key}: "
                f"inserted={result['inserted']}, skipped={result['skipped']}"
            )
            processed += 1

        except Exception as exc:
            logger.error(f"Failed to process {s3_key}: {exc}", exc_info=True)
            mark_failed(etag)
            failed += 1

    logger.info(f"=== Ingestion complete: processed={processed}, failed={failed} ===")
    return {"processed": processed, "failed": failed}


if __name__ == "__main__":
    result = run_ingestion()
    sys.exit(1 if result["failed"] > 0 else 0)
