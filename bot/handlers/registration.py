from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import FSMI18nMiddleware
from aiogram.utils.i18n import gettext as _

from bot.forms import fields
from bot.forms.states import Registration
from bot.keyboards.profile import (
    ChatAddableCB,
    PackagesDoneCB,
    ProfileField,
    SetLanguageCB,
    WithCodesCB,
)
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.pack_price_limits import PackPriceLimitRepository
from common.services.moderation import ModerationService

router = Router(name="registration")


@router.callback_query(Registration.language, SetLanguageCB.filter())
async def process_language(
    callback: CallbackQuery,
    callback_data: SetLanguageCB,
    state: FSMContext,
    i18n_middleware: FSMI18nMiddleware,
) -> None:
    await i18n_middleware.set_locale(state=state, locale=callback_data.value)
    await state.set_state(Registration.chat_addable)
    await callback.message.edit_reply_markup(reply_markup=None)
    await fields.send_prompt(callback.message, ProfileField.chat_addable)
    await callback.answer()


@router.callback_query(Registration.chat_addable, ChatAddableCB.filter())
async def process_chat_addable(
    callback: CallbackQuery,
    callback_data: ChatAddableCB,
    state: FSMContext,
) -> None:
    await fields.apply_chat_addable(state=state, value=callback_data.value)
    await state.set_state(Registration.with_codes)
    await callback.message.edit_reply_markup(reply_markup=None)
    await fields.send_prompt(callback.message, ProfileField.with_codes)
    await callback.answer()


@router.callback_query(Registration.with_codes, WithCodesCB.filter())
async def process_with_codes(
    callback: CallbackQuery,
    callback_data: WithCodesCB,
    state: FSMContext,
) -> None:
    await fields.apply_with_codes(state=state, value=callback_data.value)
    if callback_data.value:
        await state.set_state(Registration.withdrawal_method)
        await callback.message.edit_reply_markup(reply_markup=None)
        await fields.send_prompt(callback.message, ProfileField.withdrawal_method, with_codes=True)
    else:
        await state.set_state(Registration.packages)
        await fields.show_packages_grid(target=callback, state=state)
    await callback.answer()


@router.callback_query(Registration.packages, PackagesDoneCB.filter())
async def process_packages_done(
    callback: CallbackQuery,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    if not await fields.ensure_packages_selected(callback=callback, state=state):
        return
    await fields.start_price_entry(
        callback=callback,
        state=state,
        pack_price_limits=pack_price_limits,
    )
    await callback.answer()


@router.message(Registration.prices, F.text)
async def process_pack_price(
    message: Message,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    if not await fields.submit_pack_price(
        message=message,
        state=state,
        pack_price_limits=pack_price_limits,
    ):
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
    moderation: ModerationService,
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
        moderation=moderation,
        moderator_ids=moderator_ids,
    )


@router.message(Registration.finished_filling)
async def process_finished_filling(message: Message) -> None:
    await message.answer(_("registration.finished_filling"))
