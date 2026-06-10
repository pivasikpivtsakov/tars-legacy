from common.repositories.bot_switch import BotSwitchRepository
from common.repositories.user_profiles import UserProfileRepository

class BotSwitchService:
    def __init__(self, *, repo: BotSwitchRepository, profiles: UserProfileRepository) -> None:
        self._repo = repo
        self._profiles = profiles

    async def is_enabled(self) -> bool:
        return await self._repo.is_enabled()
    
    async def enable(self) -> None:
        await self._repo.enable()

    async def disable(self) -> None:
        await self._repo.disable()
        await self._profiles.go_everyone_full_offline()
