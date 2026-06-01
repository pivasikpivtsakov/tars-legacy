import contextlib
from typing import Any

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
from common.repositories.orders import Order
from common.repositories.user_profiles import UserProfile
from common.services.order_processing import OrderLifecycle, TakeStatus

router = Router(name="orders")


def _format_codes(codes: Any) -> str:
    if isinstance(codes, list):
        joined = ", ".join(str(code) for code in codes)
    else:
        joined = str(codes)
    return _("order.codes_line").format(codes=joined)


async def _render_taken(
    *,
    callback: CallbackQuery,
    order: Order,
    profile: UserProfile,
) -> None:
    text = _("order.taken").format(
        order_id=order.id,
        amount=order.amount,
        pubg_id=order.pubg_id,
    )
    if profile.with_codes and order.codes:
        text = f"{text}\n{_format_codes(order.codes)}"
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
        user_id=callback.from_user.id,
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
) -> None:
    order = await order_lifecycle.complete(
        order_id=callback_data.order_id,
        user_id=callback.from_user.id,
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
) -> None:
    order = await order_lifecycle.cancel(
        order_id=callback_data.order_id,
        user_id=callback.from_user.id,
    )
    if order is None:
        await callback.answer(_("order.unavailable"), show_alert=True)
        return
    await _finalize(callback=callback, text=_("order.cancelled").format(order_id=order.id))
    await callback.answer()


@router.callback_query(NoopCB.filter())
async def noop_order(callback: CallbackQuery) -> None:
    await callback.answer()
