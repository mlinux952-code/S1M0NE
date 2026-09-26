"""
core/logging_setup.py — Logging Manager de S1M0NE.

Règles appliquées (mega-prompt §21) :
- Niveaux DEBUG/INFO/WARNING/ERROR/CRITICAL.
- Rotation automatique pour ne jamais remplir le disque.
- Jamais de secrets/tokens/mots de passe en clair dans les logs (filtre appliqué).
- Sortie simultanée : fichier (logs/s1mone.log, avec rotation) + console (Rich si dispo).
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.config import settings

_SENSITIVE_PATTERN = re.compile(
    r"(?i)(token|api[_-]?key|secret|password|passwd)\s*[=:]\s*([^\s,'\"]+)"
)


class RedactSensitiveFilter(logging.Filter):
    """Empêche qu'une clé API/token/mot de passe apparaisse en clair dans un message de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _SENSITIVE_PATTERN.sub(r"\1=***MASKED***", record.msg)
        return True


_configured = False


def configure_logging(logger_name: str = "s1mone") -> logging.Logger:
    global _configured
    logger = logging.getLogger(logger_name)

    if _configured:
        return logger

    logs_dir: Path = settings.logs_dir
    logs_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level, logging.INFO)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        logs_dir / "s1mone.log",
        maxBytes=settings.log_max_bytes,
        backupCount=settings.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactSensitiveFilter())

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(RedactSensitiveFilter())

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    _configured = True
    return logger


def get_logger(name: str = "s1mone") -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
