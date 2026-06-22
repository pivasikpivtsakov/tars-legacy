from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from common.repositories.user_roles import UserRole, UserRoleRepository


class RoleContextMiddleware(BaseMiddleware):
    def __init__(self, *, roles: UserRoleRepository) -> None:
        self._roles = roles

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        role_ids = await self._roles.get_all()
        data["admin_ids"] = role_ids[UserRole.ADMIN]
        data["moderator_ids"] = role_ids[UserRole.MODERATOR]
        return await handler(event, data)
