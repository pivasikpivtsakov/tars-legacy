import logging

from colorlog import ColoredFormatter
from pythonjsonlogger.core import RESERVED_ATTRS
from pythonjsonlogger.json import JsonFormatter

from common.environment import AIOGRAM_EVENT_LOG_LEVEL, LOG_FORMAT, LOG_LEVEL
from common.log_context import current_update_id, current_user_id

# LogRecord attr -> Grafana/output key. The complete set of fields every line can carry.
_LOGRECORD_TO_GRAFANA = {
    "asctime": "timestamp",
    "levelname": "level",
    "name": "logger",
    "lineno": "line",
    "user_id": "user_id",
    "update_id": "update_id",
    "message": "message",
}
# Set from contextvars per request; absent outside a bot update.
_CONTEXT_ATTRS = ("user_id", "update_id")
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
# Per-field colorlog color for console output (keyed like _LOGRECORD_TO_GRAFANA).
# log_color/message_log_color resolve per level; cyan/blue are static.
_CONSOLE_COLORS = {
    "asctime": "log_color",
    "levelname": "log_color",
    "name": "cyan",
    "lineno": "cyan",
    "user_id": "blue",
    "update_id": "blue",
    "message": "message_log_color",
}


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.user_id = current_user_id()
        record.update_id = current_update_id()
        return True


def _json_formatter() -> JsonFormatter:
    fmt = " ".join(f"%({attr})s" for attr in _LOGRECORD_TO_GRAFANA)
    return JsonFormatter(
        fmt=fmt,
        datefmt=_DATE_FMT,
        rename_fields=_LOGRECORD_TO_GRAFANA,
        reserved_attrs=[*RESERVED_ATTRS, "color_message"],
        defaults=dict.fromkeys(_CONTEXT_ATTRS),
    )


def _colored_formatter(*, with_context: bool) -> ColoredFormatter:
    attrs = [
        attr
        for attr in _LOGRECORD_TO_GRAFANA
        if with_context or attr not in _CONTEXT_ATTRS
    ]
    fmt = " ".join(f"%({_CONSOLE_COLORS[attr]})s%({attr})s%(reset)s" for attr in attrs)
    return ColoredFormatter(
        fmt=fmt,
        datefmt=_DATE_FMT,
        log_colors=_LEVEL_COLORS,
        secondary_log_colors=_MESSAGE_COLORS,
    )


class _ConsoleFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__()
        self._with_context = _colored_formatter(with_context=True)
        self._without_context = _colored_formatter(with_context=False)

    def format(self, record: logging.LogRecord) -> str:
        has_context = any(getattr(record, attr, None) is not None for attr in _CONTEXT_ATTRS)
        return (self._with_context if has_context else self._without_context).format(record)


def setup_logging(level: str | None = None) -> None:
    resolved_level = (level or LOG_LEVEL or "INFO").upper()

    handler = logging.StreamHandler()
    handler.setFormatter(_ConsoleFormatter() if LOG_FORMAT == "console" else _json_formatter())
    handler.addFilter(_ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    logging.getLogger("aiogram.event").setLevel((AIOGRAM_EVENT_LOG_LEVEL or "WARNING").upper())
