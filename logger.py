"""Logging configuration for console and file output."""

from __future__ import annotations

import logging
from logging import Logger

from config import LOG_PATH, ensure_directories


def setup_logger(name: str = "rate_sync") -> Logger:
    """Configure and return the application logger.

    Args:
        name: Logger name.

    Returns:
        Configured logger writing to console and logs/app.log.
    """
    ensure_directories()

    logger: Logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter: logging.Formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler: logging.StreamHandler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    file_handler: logging.FileHandler = logging.FileHandler(
        LOG_PATH,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    logger.propagate = False

    return logger


def get_logger(name: str = "rate_sync") -> Logger:
    """Return an existing logger, creating it if needed.

    Args:
        name: Logger name.

    Returns:
        Application logger instance.
    """
    logger: Logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
