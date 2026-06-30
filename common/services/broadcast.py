import asyncio
import logging
from collections.abc import Collection, Iterable
from itertools import batched

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.repositories.postgres.user_profiles import UserProfileRepository

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 25


class BroadcastService:
    def __init__(self, *, profiles: UserProfileRepository) -> None:
        self._profiles = profiles

    async def send_to_everyone(self, *, bot: Bot, text: str) -> int:
        tg_ids = await self._profiles.all_tg_ids()
        return await self._deliver(bot=bot, tg_ids=tg_ids, text=text)

    async def send_to_tg_ids(self, *, bot: Bot, tg_ids: Collection[int], text: str) -> int:
        return await self._deliver(bot=bot, tg_ids=tg_ids, text=text)

    async def send_to_user_ids(self, *, bot: Bot, user_ids: Collection[int], text: str) -> int:
        resolved = await self._profiles.get_tg_ids(profile_ids=user_ids)
        return await self._deliver(bot=bot, tg_ids=resolved.values(), text=text)

    async def _deliver(self, *, bot: Bot, tg_ids: Iterable[int], text: str) -> int:
        delivered = 0
        for chunk in batched(tg_ids, _CHUNK_SIZE, strict=False):
            results = await asyncio.gather(
                *(self._send_one(bot=bot, tg_id=tg_id, text=text) for tg_id in chunk),
            )
            delivered += sum(results)
        return delivered

    async def _send_one(self, *, bot: Bot, tg_id: int, text: str) -> bool:
        try:
            await bot.send_message(chat_id=tg_id, text=text)
        except TelegramAPIError:
            logger.exception("broadcast failed for tg_id=%s", tg_id)
            return False
        return True
