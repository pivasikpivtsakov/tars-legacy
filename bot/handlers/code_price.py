from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.forms.states import CodeOrderPrice
from bot.handlers.pack_limits import _is_staff
from bot.keyboards.code_price import (
    CodePriceCancelCB,
    CodePriceEditCB,
    code_price_kb,
    code_price_prompt_kb,
)
from bot.keyboards.start import OpenZoneCB, StartZone
from common.money import format_money, parse_money
from common.repositories.redis.code_order_price import CodeOrderPriceRepository

router = Router(name="code_price")

_PRICE_MSG_KEY = "code_price_msg_id"


def _parse_price(raw: str) -> Decimal | None:
    value = parse_money(raw)
    if value is None or value <= 0:
        return None
    return value


def _panel_view(price: Decimal) -> tuple[str, InlineKeyboardMarkup]:
    return (
        _("admin.code_price_title").format(price=format_money(price)),
        code_price_kb(
            edit_text=_("admin.btn_code_price_edit"),
            back_text=_("start.btn_back"),
        ),
    )


async def _render_panel(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    code_order_price: CodeOrderPriceRepository,
) -> None:
    await state.set_state(None)
    text, markup = _panel_view(await code_order_price.get())
    await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.CODE_ORDER_PRICE), _is_staff)
async def open_code_price(
    callback: CallbackQuery,
    state: FSMContext,
    code_order_price: CodeOrderPriceRepository,
) -> None:
    await _render_panel(callback=callback, state=state, code_order_price=code_order_price)
    await callback.answer()


@router.callback_query(CodePriceEditCB.filter(), _is_staff)
async def prompt_code_price(
    callback: CallbackQuery,
    state: FSMContext,
    code_order_price: CodeOrderPriceRepository,
) -> None:
    current = await code_order_price.get()
    await state.set_state(CodeOrderPrice.awaiting_value)
    await state.update_data({_PRICE_MSG_KEY: callback.message.message_id})
    await callback.message.edit_text(
        _("admin.code_price_prompt").format(current=format_money(current)),
        reply_markup=code_price_prompt_kb(cancel_text=_("registration.btn_cancel_pack")),
    )
    await callback.answer()


@router.callback_query(CodePriceCancelCB.filter(), _is_staff)
async def cancel_code_price(
    callback: CallbackQuery,
    state: FSMContext,
    code_order_price: CodeOrderPriceRepository,
) -> None:
    await _render_panel(callback=callback, state=state, code_order_price=code_order_price)
    await callback.answer()


@router.message(CodeOrderPrice.awaiting_value, F.text)
async def apply_code_price(
    message: Message,
    state: FSMContext,
    code_order_price: CodeOrderPriceRepository,
) -> None:
    value = _parse_price(message.text)
    if value is None:
        await message.answer(_("admin.code_price_invalid"))
        return
    data = await state.get_data()
    await code_order_price.set(price=value)
    await state.set_state(None)
    text, markup = _panel_view(value)
    message_id = data.get(_PRICE_MSG_KEY)
    if message_id is not None:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=message_id,
                reply_markup=markup,
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=markup)
