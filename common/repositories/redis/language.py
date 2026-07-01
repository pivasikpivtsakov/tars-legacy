import json

from redis.asyncio import Redis

from common.i18n import LOCALE_FSM_KEY

_FSM_DATA_KEY = "aiogram_fsm:{tg_id}:{tg_id}:default:data"


class LanguageRepository:
    def __init__(self, *, redis: Redis, default_locale: str) -> None:
        self._redis = redis
        self._default_locale = default_locale

    async def get(self, *, tg_id: int) -> str:
        raw = await self._redis.get(_FSM_DATA_KEY.format(tg_id=tg_id))
        if raw is None:
            return self._default_locale
        return json.loads(raw).get(LOCALE_FSM_KEY, self._default_locale)
