from common.models.user_profiles import UserProfile, UserProfileStatus
from common.repositories.user_profiles import UserProfileRepository


class UserProfileService:
    def __init__(self, *, repo: UserProfileRepository) -> None:
        self._repo = repo

    async def block(self, *, profile_id: int) -> UserProfile:
        return await self._repo.set_status(
            profile_id=profile_id,
            status=UserProfileStatus.BANNED,
        )
