"""Structured (JSON) logging via structlog.

Every log line automatically carries whatever's bound to the current
request's context — request_id always (see app.middleware.request_id),
tenant_id/user_id once auth resolves (see app.core.security) — without
every call site having to pass them explicitly.
"""

import logging
import sys

import structlog
from structlog.types import Processor

from app.core.config import get_settings


def configure_logging() -> None:
    settings = get_settings()
    is_dev = settings.environment == "development"

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer: Processor = (
        structlog.dev.ConsoleRenderer() if is_dev else structlog.processors.JSONRenderer()
    )
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO if not is_dev else logging.DEBUG)

    # Quiet the very chatty libraries down to warnings-and-up.
    for noisy_logger in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
