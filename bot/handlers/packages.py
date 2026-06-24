from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.forms import fields
from bot.forms.states import (
    PACKAGES_STATE_BY_PRICES,
    PACKAGES_STATES,
    PRICES_STATES,
)
from bot.keyboards.profile import PackCancelCB, PackTapCB

router = Router(name="packages")


@router.callback_query(StateFilter(*PACKAGES_STATES), PackTapCB.filter())
async def pack_tap(
    callback: CallbackQuery,
    callback_data: PackTapCB,
    state: FSMContext,
) -> None:
    await fields.toggle_pack(callback=callback, state=state, value=callback_data.value)
    await callback.answer()


@router.callback_query(StateFilter(*PACKAGES_STATES, *PRICES_STATES), PackCancelCB.filter())
async def pack_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    packages_state = PACKAGES_STATE_BY_PRICES.get(await state.get_state())
    if packages_state is not None:
        await state.set_state(packages_state)
    await fields.cancel_pack(callback=callback, state=state)
    await callback.answer()


@router.message(StateFilter(*PACKAGES_STATES), F.text)
async def pack_text_reminder(message: Message) -> None:
    await message.answer(_("registration.pack_use_buttons"))
