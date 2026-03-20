from __future__ import annotations

import logging
import os
import sys
import time


def setup_logging(name: str = "ece496") -> logging.Logger:
    """
    Standard logging across scripts.
    Env:
      LOG_LEVEL=DEBUG|INFO|WARNING|ERROR
    """
    level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
            "%Y-%m-%dT%H:%M:%SZ",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)

    logging.Formatter.converter = time.gmtime  # UTC timestamps
    return logger
