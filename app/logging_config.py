"""Logging setup.

Rule: never log tokens or passwords. Our own log lines only reference
session_id (a UUID that cannot authenticate). Uvicorn, however, logs the
raw WebSocket URL including ?token=..., so a filter redacts it.
"""

import logging
import re

_TOKEN_IN_URL = re.compile(r"(token=)[^&\s\"']+")


class RedactTokenFilter(logging.Filter):
    """Replace token query-string values with *** in a record's final message."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = _TOKEN_IN_URL.sub(r"\1***", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure app logging and install token redaction on uvicorn's loggers."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("app").setLevel(level.upper())

    for name in ("uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not any(isinstance(f, RedactTokenFilter) for f in logger.filters):
            logger.addFilter(RedactTokenFilter())
