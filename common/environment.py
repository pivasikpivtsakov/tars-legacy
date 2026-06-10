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
    "TELEGRAM_BOT_TOKEN",
    warning_message="obtain TELEGRAM_BOT_TOKEN from @BotFather"
)


def _parse_id_set(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()
    return frozenset(int(part) for part in value.split(",") if part.strip())


ADMIN_USER_IDS = _parse_id_set(
    env_get("ADMIN_USER_IDS", default="", raise_if_failed=False),
)

MODERATOR_USER_IDS = _parse_id_set(
    env_get("MODERATOR_USER_IDS", default="", raise_if_failed=False),
)


def _env_positive_int(varname: str, *, default: int) -> int:
    return int(
        env_get(
            varname,
            default=str(default),
            validation_rule=lambda val: val.isdigit() and int(val) > 0,
            warning_message=f"{varname} must be a positive integer",
            raise_if_failed=True,
        )
    )


# How often the dispatcher sweeps with no wake signal (backstop for missed wakes).
DISPATCH_BACKSTOP_SECONDS = _env_positive_int("DISPATCH_BACKSTOP_SECONDS", default=30)
# Max orders pulled from the backlog per sweep (bounds per-sweep cost).
DISPATCH_BATCH_LIMIT = _env_positive_int("DISPATCH_BATCH_LIMIT", default=100)
# How often the timekeeper polls the offer-deadline queue for due expiries.
OFFER_EXPIRY_POLL_SECONDS = _env_positive_int("OFFER_EXPIRY_POLL_SECONDS", default=1)
OFFER_TTL_SECONDS = _env_positive_int("OFFER_TTL_SECONDS", default=30)
RATING_SPEED_WINDOW = _env_positive_int("RATING_SPEED_WINDOW", default=3)
MAX_ORDERS_PENDING = _env_positive_int("MAX_ORDERS_PENDING", default=3)
FANOUT_CHUNK_SIZE = _env_positive_int("FANOUT_CHUNK_SIZE", default=20)
OFFER_RECONCILE_GRACE_SECONDS = _env_positive_int("OFFER_RECONCILE_GRACE_SECONDS", default=15)
