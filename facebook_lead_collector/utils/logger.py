"""Logging configuration for Facebook Lead Collector."""
import logging
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class CustomFormatter(logging.Formatter):
    """Custom formatter producing format: YYYY-MM-DD HH:MM:SS | LEVEL | Message."""

    def __init__(self, fmt: str = "%(asctime)s | %(levelname)s | %(message)s", datefmt: str = "%Y-%m-%d %H:%M:%S"):
        super().__init__(fmt=fmt, datefmt=datefmt)


def setup_logger(
    name: str = "facebook_lead_collector",
    level: str = "INFO",
    log_to_file: bool = False,
    log_dir: str | Path = "logs",
) -> logging.Logger:
    """Set up and return a configured logger instance.

    Args:
        name: Logger name.
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_to_file: Whether to save logs to a file.
        log_dir: Directory where log files are stored if enabled.

    Returns:
        Configured Logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if setup_logger is called multiple times
    if logger.handlers:
        return logger

    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(log_level)

    formatter = CustomFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Optional file handler
    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path / "collector.log", encoding="utf-8")
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


# Default logger instance
logger = setup_logger()
