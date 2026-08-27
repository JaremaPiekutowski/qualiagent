"""Colored console logging setup."""

import logging

import colorlog

LOGGING_CONFIGURED = False


def configure_console_logging(level: str = "INFO") -> None:
    """Configure the root logger with colorlog once.

    Args:
        level: Logging level name, for example ``INFO`` or ``DEBUG``.
    """
    global LOGGING_CONFIGURED
    if LOGGING_CONFIGURED:
        return

    handler = colorlog.StreamHandler()
    handler.setFormatter(
        colorlog.ColoredFormatter(
            fmt="%(log_color)s%(levelname)-8s%(reset)s %(blue)s%(name)s%(reset)s %(message)s",
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    LOGGING_CONFIGURED = True
