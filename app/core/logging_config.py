"""
Logging configuration for SplitVice.

- Development: human-readable format with colours (standard logging)
- Production: JSON-structured format for log aggregators

Call configure_logging() once at startup (in main.py lifespan).
"""

import logging
import sys
from app.core.config import settings


def configure_logging() -> None:
    """Set up root logger based on ENV."""
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    if settings.is_production:
        # JSON-structured format — easy to parse by Datadog, CloudWatch, etc.
        fmt = (
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"logger":"%(name)s","message":"%(message)s"}'
        )
    else:
        # Human-readable for local development
        fmt = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"

    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,  # override any existing handlers (e.g. uvicorn's)
    )

    # Quieten noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.INFO)
