import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from common.i18n import build_i18n
from common.keyboards.orders import take_inline_kb
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import Order, OrderRepository
from common.repositories.rating import RatingRepository
from common.services.order_processing import OrderManager, forward_to_third_party

logger = logging.getLogger(__name__)

_i18n = build_i18n()
_ = _i18n.gettext


async def offer_order_to_next_user(  # noqa: PLR0913
    *,
    order: Order,
    bot: Bot,
    orders: OrderRepository,
    offers: OrderOfferRepository,
    order_manager: OrderManager,
    rating: RatingRepository,
) -> None:
    already_offered_user_ids = await offers.offered_user_ids(order_id=order.id)
    ranked_candidates = await order_manager.select_candidates(
        order=order,
        exclude_user_ids=already_offered_user_ids,
    )
    if not ranked_candidates:
        await orders.mark_no_takers(order_id=order.id)
        expired_user_ids = await offers.expire_offered(order_id=order.id)
        # todo: надо ли здесь записывать не взятых? разве мы не записали их раньше?
        await rating.record_not_taken(user_ids=expired_user_ids)
        await forward_to_third_party(order=order)
        return
    next_recipient = ranked_candidates[0]
    await offers.record_offer(order_id=order.id, user_id=next_recipient.user_id)
    try:
        await bot.send_message(
            chat_id=next_recipient.user_id,
            text=render_offer_text(order=order, full_price=next_recipient.full_price),
            reply_markup=take_inline_kb(
                order_id=order.id,
                take_text=_("order.btn_take"),
            ),
        )
    except TelegramAPIError:
        logger.exception(
            "failed to deliver offer order_id=%s user_id=%s",
            order.id,
            next_recipient.user_id,
        )
    await orders.mark_offering(order_id=order.id)


def render_offer_text(*, order: Order, full_price: int) -> str:
    return _("order.offer").format(
        order_id=order.id,
        amount=order.amount,
        full_price=full_price,
    )
