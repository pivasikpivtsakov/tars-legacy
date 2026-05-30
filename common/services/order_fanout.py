import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import Order, OrderRepository
from common.services.order_processing import OrderManager

logger = logging.getLogger(__name__)


async def offer_order_to_next_user(
    *,
    order: Order,
    bot: Bot,
    orders: OrderRepository,
    offers: OrderOfferRepository,
    order_manager: OrderManager,
) -> None:
    already_offered_user_ids = await offers.offered_user_ids(order_id=order.id)
    ranked_candidates = await order_manager.select_candidates(
        order=order,
        exclude_user_ids=already_offered_user_ids,
    )
    if not ranked_candidates:
        await orders.mark_no_takers(order_id=order.id)
        await forward_to_third_party(order=order)
        return
    next_recipient = ranked_candidates[0]
    await offers.record_offer(order_id=order.id, user_id=next_recipient.user_id)
    try:
        await bot.send_message(
            chat_id=next_recipient.user_id,
            text=render_offer_text(order=order, full_price=next_recipient.full_price),
            reply_markup=take_inline_kb(order_id=order.id),
        )
    except TelegramAPIError:
        logger.exception(
            "failed to deliver offer order_id=%s user_id=%s",
            order.id,
            next_recipient.user_id,
        )
    await orders.mark_offering(order_id=order.id)


async def forward_to_third_party(*, order: Order) -> None:
    logger.info("third-party hand-off requested order_id=%s", order.id)


def render_offer_text(*, order: Order, full_price: int) -> str:
    return (
        "<b>Новый заказ</b>\n"
        f"UC: <b>{order.amount}</b>\n"
        f"Цена: <b>{full_price}</b>"
    )


def take_inline_kb(*, order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Взять",
                    callback_data=f"take_order:{order_id}",
                ),
            ],
        ],
    )
