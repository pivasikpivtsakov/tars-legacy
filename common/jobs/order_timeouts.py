from common.jobs.registry import get_order_timeouts


async def order_expiry_notification_1(*, order_id: int, user_id: int, chat_id: int) -> None:
    await get_order_timeouts().run_order_expiry_notification_1(
        order_id=order_id, user_id=user_id, chat_id=chat_id
    )


async def order_expiry_notification_2(*, order_id: int, user_id: int, chat_id: int) -> None:
    await get_order_timeouts().run_order_expiry_notification_2(
        order_id=order_id, user_id=user_id, chat_id=chat_id
    )


async def order_expiry(*, order_id: int, user_id: int) -> None:
    await get_order_timeouts().run_order_expiry(order_id=order_id, user_id=user_id)
