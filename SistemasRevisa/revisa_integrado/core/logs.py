import logging
from logging.handlers import RotatingFileHandler

from . import paths

LOGGER_NAME = "sistemas_revisa"


def setup_logging(folder=None):
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    folder = folder or paths.logs_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder / "sistemas_revisa.log", maxBytes=1_000_000,
                                      backupCount=5, encoding="utf-8")
    except OSError:
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


def get_logger():
    return logging.getLogger(LOGGER_NAME)
