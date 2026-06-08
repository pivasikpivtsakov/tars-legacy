from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.forms import fields
from bot.forms.states import Registration
from bot.keyboards.profile import (
    PackagesDoneCB,
    PackageToggleCB,
    ProfileField,
    WorksAloneCB,
)
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository

router = Router(name="registration")


@router.callback_query(Registration.works_alone, WorksAloneCB.filter())
async def process_works_alone(
    callback: CallbackQuery,
    callback_data: WorksAloneCB,
    state: FSMContext,
) -> None:
    await fields.apply_works_alone(state=state, value=callback_data.value)
    await state.set_state(Registration.packages)
    await callback.message.edit_reply_markup(reply_markup=None)
    await fields.send_prompt(callback.message, ProfileField.packages, selected=())
    await callback.answer()


@router.callback_query(Registration.packages, PackageToggleCB.filter())
async def process_package_toggle(
    callback: CallbackQuery,
    callback_data: PackageToggleCB,
    state: FSMContext,
) -> None:
    await fields.toggle_and_render(callback=callback, state=state, value=callback_data.value)
    await callback.answer()


@router.callback_query(Registration.packages, PackagesDoneCB.filter())
async def process_packages_done(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not await fields.ensure_packages_selected(callback=callback, state=state):
        return
    await state.set_state(Registration.price_60)
    await callback.message.edit_reply_markup(reply_markup=None)
    await fields.send_prompt(callback.message, ProfileField.price_60)
    await callback.answer()


@router.message(Registration.price_60, F.text)
async def process_price(message: Message, state: FSMContext) -> None:
    if not await fields.apply_price(message=message, state=state):
        return
    await state.set_state(Registration.withdrawal_method)
    await fields.send_prompt(message, ProfileField.withdrawal_method)


@router.message(Registration.withdrawal_method, F.text)
async def process_withdrawal_method(message: Message, state: FSMContext) -> None:
    await fields.apply_withdrawal(state=state, text=message.text)
    await state.set_state(Registration.work_start)
    await fields.send_prompt(message, ProfileField.work_start)


@router.message(Registration.work_start, F.text)
async def process_work_start(message: Message, state: FSMContext) -> None:
    if not await fields.apply_work_start(message=message, state=state):
        return
    await state.set_state(Registration.work_end)
    await fields.send_prompt(message, ProfileField.work_end)


@router.message(Registration.work_end, F.text)
async def process_work_end(
    message: Message,
    state: FSMContext,
    bot: Bot,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    moderator_ids: frozenset[int],
) -> None:
    if (await state.get_data()).get("work_start") is None:
        await state.set_state(Registration.work_start)
        await fields.send_prompt(message, ProfileField.work_start)
        return
    if not await fields.apply_work_end(message=message, state=state):
        return
    await fields.finish_registration(
        message=message,
        state=state,
        bot=bot,
        profiles=profiles,
        online_price_index=online_price_index,
        moderator_ids=moderator_ids,
    )


@router.message(Registration.finished_filling)
async def process_finished_filling(message: Message) -> None:
    await message.answer(_("registration.finished_filling"))
