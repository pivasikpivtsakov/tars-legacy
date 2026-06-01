from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class TakeOrderCB(CallbackData, prefix="take_order"):
    order_id: int


class ReadyOrderCB(CallbackData, prefix="ready_order"):
    order_id: int


class CancelOrderCB(CallbackData, prefix="cancel_order"):
    order_id: int


class NoopCB(CallbackData, prefix="noop"):
    pass


def take_inline_kb(*, order_id: int, take_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=take_text,
                    callback_data=TakeOrderCB(order_id=order_id).pack(),
                ),
            ],
        ],
    )


def working_inline_kb(
    *,
    order_id: int,
    ready_text: str,
    cancel_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ready_text,
                    callback_data=ReadyOrderCB(order_id=order_id).pack(),
                ),
                InlineKeyboardButton(
                    text=" ",
                    callback_data=NoopCB().pack(),
                ),
                InlineKeyboardButton(
                    text=cancel_text,
                    callback_data=CancelOrderCB(order_id=order_id).pack(),
                ),
            ],
        ],
    )
