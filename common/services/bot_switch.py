from common.repositories.bot_switch import BotSwitchRepository
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository


class BotSwitchService:
    def __init__(
        self,
        *,
        repo: BotSwitchRepository,
        profiles: UserProfileRepository,
        online_price_index: OnlinePriceIndex,
    ) -> None:
        self._repo = repo
        self._profiles = profiles
        self._online_price_index = online_price_index

    async def is_enabled(self) -> bool:
        return await self._repo.is_enabled()

    async def enable(self) -> None:
        await self._repo.enable()

    async def disable(self) -> None:
        await self._repo.disable()
        await self._profiles.go_everyone_full_offline()
        await self._online_price_index.clear()

    async def toggle(self) -> bool:
        if await self.is_enabled():
            await self.disable()
            return False
        await self.enable()
        return True
