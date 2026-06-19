import logging
from collections.abc import Collection
from datetime import time

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.keyboards.moderation import moderation_decision_kb
from common.models.user_profiles import UserProfile
from common.packages import format_prices
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository

logger = logging.getLogger(__name__)

_TIME_FORMAT = "%H:%M"


def _fmt_time(value: time | None) -> str:
    return value.strftime(_TIME_FORMAT) if value is not None else "-"


def _fmt_packages(packages: tuple[int, ...] | None) -> str:
    return ", ".join(str(pkg) for pkg in packages) if packages else "-"


def _fmt_yes_no(value: bool | None) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def render_pending_review(*, profile: UserProfile) -> str:
    return (
        "#pending user awaiting moderation\n"
        f"tg_id: {profile.tg_id}\n"
        f"works alone: {_fmt_yes_no(profile.works_alone)}\n"
        f"with codes: {_fmt_yes_no(profile.with_codes)}\n"
        f"packages: {_fmt_packages(profile.packages)}\n"
        f"prices: {format_prices(profile.prices)}\n"
        f"withdrawal: {profile.withdrawal_method or '-'}\n"
        f"work hours: {_fmt_time(profile.work_start)}-{_fmt_time(profile.work_end)}"
    )


async def _broadcast(
    *,
    bot: Bot,
    moderator_ids: Collection[int],
    profiles: UserProfileRepository,
    profile: UserProfile,
) -> None:
    text = render_pending_review(profile=profile)
    markup = moderation_decision_kb(
        profile_id=profile.id,
        with_codes=profile.with_codes,
    )
    tg_ids = await profiles.get_tg_ids(profile_ids=moderator_ids)
    for moderator_id in moderator_ids:
        tg_id = tg_ids.get(moderator_id)
        if tg_id is None:
            logger.warning(
                "cannot resolve tg_id for moderator_id=%s profile_id=%s",
                moderator_id,
                profile.id,
            )
            continue
        try:
            await bot.send_message(
                chat_id=tg_id,
                text=text,
                reply_markup=markup,
            )
        except TelegramAPIError:
            logger.exception(
                "failed to notify moderator_id=%s tg_id=%s profile_id=%s",
                moderator_id,
                tg_id,
                profile.id,
            )


async def is_moderator(
    *,
    profiles: UserProfileRepository,
    moderator_ids: Collection[int],
    tg_id: int,
) -> bool:
    if not moderator_ids:
        return False
    profile = await profiles.get_by_tg_id(tg_id=tg_id)
    return profile is not None and profile.id in moderator_ids


async def deactivate_and_notify(
    *,
    bot: Bot,
    moderator_ids: Collection[int],
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    profile: UserProfile,
) -> UserProfile:
    updated = await profiles.deactivate(profile_id=profile.id)
    await online_price_index.remove(user_id=updated.id)
    await _broadcast(
        bot=bot,
        moderator_ids=moderator_ids,
        profiles=profiles,
        profile=updated,
    )
    return updated
