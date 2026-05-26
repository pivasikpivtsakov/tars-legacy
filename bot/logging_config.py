import logging
import os

from colorlog import ColoredFormatter

_FMT = (
    "%(log_color)s%(asctime)s%(reset)s "
    "%(log_color)s%(levelname)-8s%(reset)s "
    "%(cyan)s%(name)s:%(lineno)d%(reset)s "
    "%(message_log_color)s%(message)s"
)
_DATE_FMT = "%Y-%m-%d %H:%M:%S"
_LEVEL_COLORS = {
    "DEBUG": "cyan",
    "INFO": "green",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold_red",
}
_MESSAGE_COLORS = {
    "message": {
        "DEBUG": "white",
        "INFO": "white",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "bold_red",
    },
}


def setup_logging(level: str | None = None) -> None:
    resolved_level = (level or os.environ.get("LOG_LEVEL", "INFO")).upper()

    handler = logging.StreamHandler()
    handler.setFormatter(
        ColoredFormatter(
            fmt=_FMT,
            datefmt=_DATE_FMT,
            log_colors=_LEVEL_COLORS,
            secondary_log_colors=_MESSAGE_COLORS,
        ),
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
