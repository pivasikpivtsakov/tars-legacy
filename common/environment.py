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
        raise_if_failed=True,
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


def _parse_admin_ids(value: str | None) -> frozenset[int]:
    if not value:
        return frozenset()
    return frozenset(int(part) for part in value.split(",") if part.strip())


ADMIN_USER_IDS = _parse_admin_ids(
    env_get("ADMIN_USER_IDS", default="", raise_if_failed=False),
)


def _is_positive_integer(value: str) -> bool:
    return value.isdigit() and int(value) > 0


SCHEDULER_INTERVAL_SECONDS = int(
    env_get(
        "SCHEDULER_INTERVAL_SECONDS",
        default="30",
        validation_rule=_is_positive_integer,
        warning_message="SCHEDULER_INTERVAL_SECONDS must be a positive integer",
        raise_if_failed=False,
    )
    or "30"
)

RATING_SPEED_WINDOW = int(
    env_get(
        "RATING_SPEED_WINDOW",
        default="3",
        validation_rule=_is_positive_integer,
        warning_message="RATING_SPEED_WINDOW must be a positive integer",
        raise_if_failed=False,
    )
    or "3"
)
