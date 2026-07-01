import contextlib

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.forms.states import OrderCancellation, UserSession
from bot.utils.telegram import ignore_not_modified
from common.i18n import gettext_for, i18n
from common.keyboards.orders import (
    CancelOrderCB,
    CancelReasonCB,
    NoopCB,
    OrderDismissCB,
    ReadyOrderCB,
    TakeOrderCB,
    cancel_reason_prompt_kb,
    working_inline_kb,
)
from common.models.orders import Order, OrderStatus
from common.models.user_profiles import UserProfile
from common.rendering.orders import render_taken_text
from common.services.anti_fraud import AntiFraudService, FraudVerdict
from common.services.broadcast import BroadcastService
from common.services.order_processing import OrderLifecycle, TakeStatus
from common.services.order_timeouts import OrderTimeoutService

router = Router(name="orders")

_CANCEL_ORDER_ID_KEY = "cancel_order_id"
_CANCEL_PROMPT_MESSAGE_ID_KEY = "cancel_prompt_message_id"


async def _render_taken(
    *,
    callback: CallbackQuery,
    order: Order,
    profile: UserProfile,
) -> str:
    text = render_taken_text(
        order=order,
        with_codes=profile.with_codes,
        gettext=_,
    )
    with ignore_not_modified():
        await callback.message.edit_text(
            text,
            reply_markup=working_inline_kb(
                order_id=order.id,
                ready_text=_("order.btn_ready"),
                noop_text=_("order.btn_noop"),
                cancel_text=_("order.btn_cancel"),
            ),
        )
    return text


async def _finalize(*, callback: CallbackQuery, text: str) -> None:
    with ignore_not_modified():
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
    default_translate = gettext_for(i18n.default_locale)
    if blocked:
        await state.set_state(UserSession.blocked)
    await broadcast.send_to_user_ids(
        bot=bot,
        user_ids=admin_ids,
        text=default_translate("order.fraud_detected").format(
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
    order_timeouts: OrderTimeoutService,
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
    taken_text = await _render_taken(callback=callback, order=result.order, profile=profile)
    await order_timeouts.start(
        order_id=result.order.id,
        user_id=profile.id,
        chat_id=callback.message.chat.id,
        message_id=callback.message.message_id,
        timed_out_text=f"{taken_text}\n{_('order.timed_out')}",
    )
    await callback.answer()


@router.callback_query(ReadyOrderCB.filter())
async def ready_order(
    callback: CallbackQuery,
    callback_data: ReadyOrderCB,
    state: FSMContext,
    bot: Bot,
    order_lifecycle: OrderLifecycle,
    order_timeouts: OrderTimeoutService,
    anti_fraud: AntiFraudService,
    broadcast: BroadcastService,
    profile: UserProfile | None,
    admin_ids: frozenset[int],
    moderator_ids: frozenset[int],
) -> None:
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    default_translate = gettext_for(i18n.default_locale)
    is_user_privileged = profile.id in admin_ids or profile.id in moderator_ids
    review = await anti_fraud.review(
        order_id=callback_data.order_id,
        profile=profile,
        block_on_fraud=not is_user_privileged,
    )
    if review.unverified_codes:
        await broadcast.send_to_user_ids(
            bot=bot,
            user_ids=moderator_ids,
            text=default_translate("order.codes_unverified_moderator").format(
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
            text=default_translate("order.check_failed_moderator").format(
                order_id=review.order.original_id,
                reason=default_translate("order.check_reason_fraud"),
                user_id=profile.id,
                tg_id=profile.tg_id,
                ban_status=default_translate("order.user_banned")
                if not is_user_privileged
                else default_translate("order.user_not_banned"),
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
            text=default_translate("order.check_failed_moderator").format(
                order_id=review.order.original_id,
                reason=default_translate("order.check_reason_not_activated"),
                user_id=profile.id,
                tg_id=profile.tg_id,
                ban_status=default_translate("order.user_not_banned"),
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
    await order_timeouts.clear(order_id=callback_data.order_id)
    await _finalize(callback=callback, text=_("order.completed").format(order_id=order.id))
    await callback.answer()


@router.callback_query(CancelOrderCB.filter())
async def cancel_order(
    callback: CallbackQuery,
    callback_data: CancelOrderCB,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    # The order stays "taken" until a reason arrives, so the expiry scheduler keeps
    # running: a user who dawdles gets cancelled by the regular timeout procedure.
    await state.set_state(OrderCancellation.awaiting_reason)
    await state.update_data(
        {
            _CANCEL_ORDER_ID_KEY: callback_data.order_id,
            _CANCEL_PROMPT_MESSAGE_ID_KEY: callback.message.message_id,
        },
    )
    with ignore_not_modified():
        await callback.message.edit_text(
            _("order.cancel_reason_prompt").format(order_id=callback_data.order_id),
            reply_markup=cancel_reason_prompt_kb(
                order_id=callback_data.order_id,
                cancel_text=_("order.btn_cancel_reason"),
            ),
        )
    await callback.answer()


@router.callback_query(CancelReasonCB.filter())
async def abort_cancel_reason(
    callback: CallbackQuery,
    callback_data: CancelReasonCB,
    state: FSMContext,
    order_lifecycle: OrderLifecycle,
    profile: UserProfile | None,
) -> None:
    await state.set_state(None)
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    order = await order_lifecycle.get(order_id=callback_data.order_id)
    if order is None or order.taken_by != profile.id or order.status is not OrderStatus.TAKEN:
        await _finalize(callback=callback, text=_("order.unavailable"))
        await callback.answer()
        return
    await _render_taken(callback=callback, order=order, profile=profile)
    await callback.answer()


@router.message(OrderCancellation.awaiting_reason, F.text)
async def submit_cancel_reason(
    message: Message,
    state: FSMContext,
    order_lifecycle: OrderLifecycle,
    order_timeouts: OrderTimeoutService,
    profile: UserProfile | None,
) -> None:
    data = await state.get_data()
    await state.set_state(None)
    order_id = data[_CANCEL_ORDER_ID_KEY]
    if profile is None:
        await message.answer(_("order.unavailable"))
        return
    order = await order_lifecycle.cancel(
        order_id=order_id,
        user_id=profile.id,
        reason=message.text.strip(),
    )
    if order is None:
        await message.answer(_("order.unavailable"))
        return
    await order_timeouts.clear(order_id=order_id)
    cancelled_text = _("order.cancelled").format(order_id=order.id)
    prompt_message_id = data.get(_CANCEL_PROMPT_MESSAGE_ID_KEY)
    if prompt_message_id is not None:
        try:
            await message.bot.edit_message_text(
                text=cancelled_text,
                chat_id=message.chat.id,
                message_id=prompt_message_id,
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(cancelled_text)


@router.callback_query(OrderDismissCB.filter())
async def dismiss_order(callback: CallbackQuery) -> None:
    with contextlib.suppress(TelegramAPIError):
        await callback.message.delete()
    await callback.answer()


@router.callback_query(NoopCB.filter())
async def noop_order(callback: CallbackQuery) -> None:
    await callback.answer()
