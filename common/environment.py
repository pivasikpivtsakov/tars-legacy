import logging
import os
from collections.abc import Callable

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def env_get(
    varname: str,
    default: str | None = None,
    validation_rule: Callable[[str], bool] | None = None,
    warning_message: str | None = None,
    raise_if_failed: bool = True,
) -> str | None:
    varvalue = os.environ.get(varname, default)
    if not varvalue:
        logger.warning(f"{varname} is unset!")
        if raise_if_failed:
            raise Exception(f"{varname} is unset!")
        return varvalue
    if validation_rule is not None and not validation_rule(varvalue):
        logger.warning(warning_message)
        if raise_if_failed:
            raise Exception(f"validation failed for {varname}")
    return varvalue


RDS_HOSTNAME = env_get("RDS_HOSTNAME")
RDS_PORT = env_get("RDS_PORT", default="5432")
RDS_USERNAME = env_get("RDS_USERNAME")
RDS_PASSWORD = env_get("RDS_PASSWORD")
RDS_DB_NAME = env_get("RDS_DB_NAME")

REDIS_URL = env_get(
    "REDIS_URL",
    default="redis://localhost:6379/0",
    raise_if_failed=False,
)

TELEGRAM_BOT_TOKEN = env_get(
    "TELEGRAM_BOT_TOKEN", warning_message="obtain TELEGRAM_BOT_TOKEN from @BotFather"
)


def _env_int(
    varname: str,
    *,
    default: int | None = None,
    positive: bool = False,
    required: bool = True,
) -> int | None:
    def validate_positive(val: str) -> bool:
        return val.isdigit() and int(val) > 0

    def validate_any(val: str) -> bool:
        return val.lstrip("-").isdigit()

    if positive:
        validation_rule = validate_positive
        int_type = "positive integer"
    else:
        validation_rule = validate_any
        int_type = "integer"
    raw = env_get(
        varname,
        default=str(default) if default is not None else None,
        validation_rule=validation_rule,
        warning_message=f"{varname} must be a {int_type}",
        raise_if_failed=required,
    )
    if raw is None:
        return None
    return int(raw)


def _env_positive_int(varname: str, *, default: int) -> int:
    return _env_int(varname, default=default, positive=True, required=True)


def _env_optional_int(varname: str) -> int | None:
    return _env_int(varname, positive=False, required=False)


def _env_boolean(varname: str, *, default: bool) -> bool:
    raw = env_get(
        varname,
        default=str(default),
        validation_rule=lambda val: val in ("True", "False", "1", "0"),
        warning_message=f"{varname} must be a boolean",
        raise_if_failed=True,
    )
    return raw in ("True", "1")


# How often the dispatcher sweeps with no wake signal (backstop for missed wakes).
DISPATCH_BACKSTOP_SECONDS = _env_positive_int("DISPATCH_BACKSTOP_SECONDS", default=30)
# Max orders pulled from the backlog per sweep (bounds per-sweep cost).
DISPATCH_BATCH_LIMIT = _env_positive_int("DISPATCH_BATCH_LIMIT", default=100)
# How often the timekeeper polls the offer-deadline queue for due expiries.
OFFER_EXPIRY_POLL_SECONDS = _env_positive_int("OFFER_EXPIRY_POLL_SECONDS", default=1)
OFFER_TTL_SECONDS = _env_positive_int("OFFER_TTL_SECONDS", default=60)
RATING_SPEED_WINDOW = _env_positive_int("RATING_SPEED_WINDOW", default=3)
MAX_ORDERS_PENDING = _env_positive_int("MAX_ORDERS_PENDING", default=3)
FANOUT_CHUNK_SIZE = _env_positive_int("FANOUT_CHUNK_SIZE", default=20)
OFFER_RECONCILE_GRACE_SECONDS = _env_positive_int("OFFER_RECONCILE_GRACE_SECONDS", default=15)
ORDER_EXPIRY_NOTIFICATION_1_DELAY_SECONDS = _env_positive_int(
    "ORDER_EXPIRY_NOTIFICATION_1_DELAY_SECONDS", default=180
)
ORDER_EXPIRY_NOTIFICATION_2_DELAY_SECONDS = _env_positive_int(
    "ORDER_EXPIRY_NOTIFICATION_2_DELAY_SECONDS", default=240
)
ORDER_EXPIRY_DELAY_SECONDS = _env_positive_int("ORDER_EXPIRY_DELAY_SECONDS", default=180)

# Telegram chat that receives cancelled/timed-out orders handed off to the long reserve.
LONG_RESERVE_CHAT_ID = _env_optional_int("LONG_RESERVE_CHAT_ID")

LOG_LEVEL = env_get("LOG_LEVEL", default="INFO", raise_if_failed=False)
LOG_FORMAT = env_get(
    "LOG_FORMAT",
    default="json",
    validation_rule=lambda val: val in ("json", "console"),
    warning_message="LOG_FORMAT must be 'json' or 'console'",
    raise_if_failed=False,
)
AIOGRAM_EVENT_LOG_LEVEL = env_get(
    "AIOGRAM_EVENT_LOG_LEVEL",
    default="WARNING",
    raise_if_failed=False,
)

APP_ENVIRONMENT = env_get("APP_ENVIRONMENT", default="production", raise_if_failed=False)

# Serve canned upstream-controller responses instead of real HTTP calls, while keeping
# ExternalOrderApi/OrderEntityService validation real. Distinct from APP_ENVIRONMENT=local,
# which short-circuits (and thus skips) that validation.
MOCK_EXTERNAL_API = _env_boolean("MOCK_EXTERNAL_API", default=False)
if MOCK_EXTERNAL_API:
    logger.warning("MOCK_EXTERNAL_API is enabled: serving canned upstream responses")

API_TOKEN = env_get("API_TOKEN")
API_URL = env_get("API_URL")
API_TIMEOUT = _env_positive_int("API_TIMEOUT", default=15)

# Bind address for the FastAPI server itself (distinct from the upstream API_URL).
API_HOST = env_get("API_HOST", default="0.0.0.0", raise_if_failed=False)
API_PORT = _env_positive_int("API_PORT", default=8000)
