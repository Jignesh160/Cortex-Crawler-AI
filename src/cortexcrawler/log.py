"""Central logging. Library code logs to the 'cortexcrawler' logger and never
configures handlers itself (apps own that). The CLI calls setup_logging().
"""
from __future__ import annotations

import logging
import os

_LOGGER_NAME = "cortexcrawler"


def get_logger(name: str | None = None) -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME if not name else f"{_LOGGER_NAME}.{name}")


def setup_logging(level: str | None = None) -> None:
    """Configure root-level handler for CLI use. Honors $CORTEX_LOG_LEVEL."""
    lvl = (level or os.getenv("CORTEX_LOG_LEVEL") or "INFO").upper()
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:  # idempotent
        logger.setLevel(lvl)
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(lvl)
    logger.propagate = False
