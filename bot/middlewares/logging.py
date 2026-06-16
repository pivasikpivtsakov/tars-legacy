from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update, User

from common.log_context import log_context


class LoggingContextMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user: User | None = data.get("event_from_user")
        update_id = event.update_id if isinstance(event, Update) else None
        with log_context(
            user_id=user.id if user is not None else None,
            update_id=update_id,
        ):
            return await handler(event, data)
