import logging
from collections.abc import Collection

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.catalog.tiers import PACK_TIERS
from common.keyboards.moderation import moderation_decision_kb
from common.models.user_profiles import UserProfile
from common.rendering.moderation import render_pending_review
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.online_index import OnlineIndexRouter

logger = logging.getLogger(__name__)


class ModerationService:
    def __init__(
        self,
        *,
        profiles: UserProfileRepository,
        online_price_index: OnlineIndexRouter,
    ) -> None:
        self._profiles = profiles
        self._online_price_index = online_price_index

    async def is_moderator(self, *, moderator_ids: Collection[int], tg_id: int) -> bool:
        if not moderator_ids:
            return False
        profile = await self._profiles.get_by_tg_id(tg_id=tg_id)
        return profile is not None and profile.id in moderator_ids

    async def is_staff(
        self,
        *,
        admin_ids: Collection[int],
        moderator_ids: Collection[int],
        tg_id: int,
    ) -> bool:
        if not admin_ids and not moderator_ids:
            return False
        profile = await self._profiles.get_by_tg_id(tg_id=tg_id)
        if profile is None:
            return False
        return profile.id in admin_ids or profile.id in moderator_ids

    async def deactivate_and_notify(
        self,
        *,
        bot: Bot,
        moderator_ids: Collection[int],
        profile: UserProfile,
    ) -> UserProfile:
        updated = await self._profiles.deactivate(profile_id=profile.id)
        await self._online_price_index.remove(user_id=updated.id)
        await self._broadcast(bot=bot, moderator_ids=moderator_ids, profile=updated)
        return updated

    async def _broadcast(
        self,
        *,
        bot: Bot,
        moderator_ids: Collection[int],
        profile: UserProfile,
    ) -> None:
        if profile.with_codes:
            tier = profile.tier
        else:
            implied = PACK_TIERS.required(profile.packages or ())
            tier = max(profile.tier, implied if implied is not None else PACK_TIERS.default())
        text = render_pending_review(profile=profile, with_codes=profile.with_codes, tier=tier)
        markup = moderation_decision_kb(
            profile_id=profile.id,
            with_codes=profile.with_codes,
            tier=tier,
        )
        tg_ids = await self._profiles.get_tg_ids(profile_ids=moderator_ids)
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
