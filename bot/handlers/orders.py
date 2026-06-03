import contextlib

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

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
    order_lifecycle: OrderLifecycle,
    profile: UserProfile | None,
) -> None:
    if profile is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
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
