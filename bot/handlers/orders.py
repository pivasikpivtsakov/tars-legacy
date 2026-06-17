import contextlib

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from bot.forms.states import UserSession
from common.keyboards.orders import (
    CancelOrderCB,
    NoopCB,
    ReadyOrderCB,
    TakeOrderCB,
    working_inline_kb,
)
from common.models.orders import Order
from common.models.user_profiles import UserProfile
from common.rendering.orders import render_taken_text
from common.services.anti_fraud import AntiFraudService, FraudVerdict
from common.services.broadcast import BroadcastService
from common.services.order_processing import OrderLifecycle, TakeStatus

router = Router(name="orders")


async def _render_taken(
    *,
    callback: CallbackQuery,
    order: Order,
    profile: UserProfile,
) -> None:
    text = render_taken_text(
        order=order,
        with_codes=profile.with_codes,
        gettext=_,
    )
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(
            text,
            reply_markup=working_inline_kb(
                order_id=order.id,
                ready_text=_("order.btn_ready"),
                cancel_text=_("order.btn_cancel"),
            ),
        )


async def _finalize(*, callback: CallbackQuery, text: str) -> None:
    with contextlib.suppress(TelegramBadRequest):
        await callback.message.edit_text(text)


async def _report_fraud(
    *,
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    broadcast: BroadcastService,
    order: Order,
    admin_ids: frozenset[int],
    blocked: bool,
) -> None:
    if blocked:
        await state.set_state(UserSession.blocked)
    await broadcast.send_to_tg_ids(
        bot=bot,
        tg_ids=admin_ids,
        text=_("order.fraud_detected").format(
            order_id=order.original_id,
            user=callback.from_user.id,
        ),
    )
    await _finalize(
        callback=callback,
        text=_("start.banned") if blocked else _("order.unfinished"),
    )
    await callback.answer()


@router.callback_query(TakeOrderCB.filter())
async def take_order(
    callback: CallbackQuery,
    callback_data: TakeOrderCB,
    order_lifecycle: OrderLifecycle,
    profile: UserProfile | None,
) -> None:
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    result = await order_lifecycle.take(
        order_id=callback_data.order_id,
        user_id=profile.id,
        profile=profile,
    )
    if result.status is TakeStatus.OFFLINE:
        await callback.answer(_("order.offline"), show_alert=True)
        return
    if result.status is TakeStatus.LIMIT_REACHED:
        await callback.answer(_("order.limit_reached"), show_alert=True)
        return
    if result.order is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    await _render_taken(callback=callback, order=result.order, profile=profile)
    await callback.answer()


@router.callback_query(ReadyOrderCB.filter())
async def ready_order(
    callback: CallbackQuery,
    callback_data: ReadyOrderCB,
    state: FSMContext,
    bot: Bot,
    order_lifecycle: OrderLifecycle,
    anti_fraud: AntiFraudService,
    broadcast: BroadcastService,
    profile: UserProfile | None,
    admin_ids: frozenset[int],
    moderator_ids: frozenset[int],
) -> None:
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    is_user_privileged = profile.tg_id in admin_ids or profile.id in moderator_ids
    review = await anti_fraud.review(
        order_id=callback_data.order_id,
        profile=profile,
        block_on_fraud=not is_user_privileged,
    )
    if review.unverified_codes:
        await broadcast.send_to_user_ids(
            bot=bot,
            user_ids=moderator_ids,
            text=_("order.codes_unverified_moderator").format(
                order_id=review.order.original_id,
                codes=", ".join(review.unverified_codes),
                user_id=profile.id,
                tg_id=profile.tg_id,
            ),
        )
    if review.verdict is FraudVerdict.FRAUD:
        await broadcast.send_to_user_ids(
            bot=bot,
            user_ids=moderator_ids,
            text=_("order.check_failed_moderator").format(
                order_id=review.order.original_id,
                reason=_("order.check_reason_fraud"),
                user_id=profile.id,
                tg_id=profile.tg_id,
                ban_status=_("order.user_banned")
                if not is_user_privileged
                else _("order.user_not_banned"),
            ),
        )
        await _report_fraud(
            callback=callback,
            bot=bot,
            state=state,
            broadcast=broadcast,
            order=review.order,
            admin_ids=admin_ids,
            blocked=not is_user_privileged,
        )
        return
    if review.verdict is FraudVerdict.UNFINISHED:
        await broadcast.send_to_user_ids(
            bot=bot,
            user_ids=moderator_ids,
            text=_("order.check_failed_moderator").format(
                order_id=review.order.original_id,
                reason=_("order.check_reason_not_activated"),
                user_id=profile.id,
                tg_id=profile.tg_id,
                ban_status=_("order.user_not_banned"),
            ),
        )
        await callback.answer(_("order.unfinished"), show_alert=True)
        return
    order = await order_lifecycle.complete(
        order_id=callback_data.order_id,
        user_id=profile.id,
    )
    if order is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    await _finalize(callback=callback, text=_("order.completed").format(order_id=order.id))
    await callback.answer()


@router.callback_query(CancelOrderCB.filter())
async def cancel_order(
    callback: CallbackQuery,
    callback_data: CancelOrderCB,
    order_lifecycle: OrderLifecycle,
    profile: UserProfile | None,
) -> None:
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    order = await order_lifecycle.cancel(
        order_id=callback_data.order_id,
        user_id=profile.id,
    )
    if order is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    await _finalize(callback=callback, text=_("order.cancelled").format(order_id=order.id))
    await callback.answer()


@router.callback_query(NoopCB.filter())
async def noop_order(callback: CallbackQuery) -> None:
    await callback.answer()
