import io
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        # Force UTF-8 on Windows where the default console encoding is cp1252
        stream = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace") \
            if hasattr(sys.stdout, "buffer") else sys.stdout
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
