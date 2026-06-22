from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.forms import fields
from bot.forms.states import (
    PACKAGES_STATE_BY_PRICES,
    PACKAGES_STATES,
    PRICES_STATE_BY_PACKAGES,
    PRICES_STATES,
)
from bot.keyboards.profile import (
    PackCancelCB,
    PackPriceCB,
    PackRemoveCB,
    PackTapCB,
)

router = Router(name="packages")


@router.callback_query(StateFilter(*PACKAGES_STATES), PackTapCB.filter())
async def pack_tap(
    callback: CallbackQuery,
    callback_data: PackTapCB,
    state: FSMContext,
) -> None:
    await fields.open_pack_panel(callback=callback, state=state, value=callback_data.value)
    await callback.answer()


@router.callback_query(StateFilter(*PACKAGES_STATES), PackPriceCB.filter())
async def pack_set_price(
    callback: CallbackQuery,
    callback_data: PackPriceCB,
    state: FSMContext,
) -> None:
    await state.set_state(PRICES_STATE_BY_PACKAGES[await state.get_state()])
    await fields.prompt_pack_price(callback=callback, state=state, value=callback_data.value)
    await callback.answer()


@router.callback_query(StateFilter(*PACKAGES_STATES), PackRemoveCB.filter())
async def pack_remove(
    callback: CallbackQuery,
    callback_data: PackRemoveCB,
    state: FSMContext,
) -> None:
    await fields.remove_pack(callback=callback, state=state, value=callback_data.value)
    await callback.answer()


@router.callback_query(StateFilter(*PACKAGES_STATES, *PRICES_STATES), PackCancelCB.filter())
async def pack_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    packages_state = PACKAGES_STATE_BY_PRICES.get(await state.get_state())
    if packages_state is not None:
        await state.set_state(packages_state)
    await fields.cancel_pack(callback=callback, state=state)
    await callback.answer()


@router.message(StateFilter(*PRICES_STATES), F.text)
async def pack_price_input(message: Message, state: FSMContext) -> None:
    if not await fields.apply_pack_price(message=message, state=state):
        return
    await state.set_state(PACKAGES_STATE_BY_PRICES[await state.get_state()])
