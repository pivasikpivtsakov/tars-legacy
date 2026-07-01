from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class TakeOrderCB(CallbackData, prefix="take_order"):
    order_id: int


class ReadyOrderCB(CallbackData, prefix="ready_order"):
    order_id: int


class CancelOrderCB(CallbackData, prefix="cancel_order"):
    order_id: int


class CancelReasonCB(CallbackData, prefix="cancel_reason"):
    order_id: int


class NoopCB(CallbackData, prefix="noop"):
    pass


class OrderDismissCB(CallbackData, prefix="order_dismiss"):
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


def cancel_reason_prompt_kb(*, order_id: int, cancel_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=cancel_text,
                    callback_data=CancelReasonCB(order_id=order_id).pack(),
                ),
            ],
        ],
    )


def working_inline_kb(
    *,
    order_id: int,
    ready_text: str,
    noop_text: str,
    cancel_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=ready_text,
                    style="success",
                    callback_data=ReadyOrderCB(order_id=order_id).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=noop_text,
                    callback_data=NoopCB().pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=cancel_text,
                    style="danger",
                    callback_data=CancelOrderCB(order_id=order_id).pack(),
                ),
            ],
        ],
    )


def checkin_inline_kb(
    *,
    order_id: int,
    yes_text: str,
    spacer_text: str,
    no_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=yes_text,
                    callback_data=OrderDismissCB().pack(),
                ),
                InlineKeyboardButton(
                    text=spacer_text,
                    callback_data=NoopCB().pack(),
                ),
                InlineKeyboardButton(
                    text=no_text,
                    style="danger",
                    callback_data=CancelOrderCB(order_id=order_id).pack(),
                ),
            ],
        ],
    )


def last_call_inline_kb(
    *,
    order_id: int,
    working_text: str,
    spacer_text: str,
    cancel_text: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=working_text,
                    callback_data=OrderDismissCB().pack(),
                ),
                InlineKeyboardButton(
                    text=spacer_text,
                    callback_data=NoopCB().pack(),
                ),
                InlineKeyboardButton(
                    text=cancel_text,
                    style="danger",
                    callback_data=CancelOrderCB(order_id=order_id).pack(),
                ),
            ],
        ],
    )
