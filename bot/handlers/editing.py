from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.forms import fields
from bot.forms.states import ProfileEdit
from bot.keyboards.profile import (
    EditFieldCB,
    EditSaveCB,
    PackagesDoneCB,
    WithCodesCB,
    WorksAloneCB,
)
from bot.keyboards.start import OpenZoneCB, StartZone
from bot.middlewares.profile import require_active_profile
from common.models.user_profiles import UserProfile
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import ModerationService

router = Router(name="editing")


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.REGISTER))
@require_active_profile
async def open_edit(
    callback: CallbackQuery,
    state: FSMContext,
    profile: UserProfile,
    moderator_ids: frozenset[int],
) -> None:
    if profile.id in moderator_ids:
        await callback.answer(_("moderation.not_order_taker"), show_alert=True)
        return
    await fields.load_profile_into_state(state=state, profile=profile)
    await fields.show_edit_menu(target=callback, state=state)
    await callback.answer()


@router.callback_query(ProfileEdit.menu, EditFieldCB.filter())
async def open_field(
    callback: CallbackQuery,
    callback_data: EditFieldCB,
    state: FSMContext,
) -> None:
    await fields.begin_field_edit(callback=callback, state=state, field=callback_data.field)
    await callback.answer()


@router.callback_query(ProfileEdit.works_alone, WorksAloneCB.filter())
async def edit_works_alone(
    callback: CallbackQuery,
    callback_data: WorksAloneCB,
    state: FSMContext,
) -> None:
    await fields.apply_works_alone(state=state, value=callback_data.value)
    await fields.show_edit_menu(target=callback, state=state)
    await callback.answer()


@router.callback_query(ProfileEdit.with_codes, WithCodesCB.filter())
async def edit_with_codes(
    callback: CallbackQuery,
    callback_data: WithCodesCB,
    state: FSMContext,
) -> None:
    await fields.apply_with_codes(state=state, value=callback_data.value)
    await fields.show_edit_menu(target=callback, state=state)
    await callback.answer()


@router.callback_query(ProfileEdit.packages, PackagesDoneCB.filter())
async def edit_packages_done(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    if not await fields.ensure_packages_selected(callback=callback, state=state):
        return
    await fields.show_edit_menu(target=callback, state=state)
    await callback.answer()


@router.message(ProfileEdit.withdrawal_method, F.text)
async def edit_withdrawal(message: Message, state: FSMContext) -> None:
    await fields.apply_withdrawal(state=state, text=message.text)
    await fields.show_edit_menu(target=message, state=state)


@router.message(ProfileEdit.work_start, F.text)
async def edit_work_start(message: Message, state: FSMContext) -> None:
    if not await fields.apply_work_start(message=message, state=state):
        return
    await fields.show_edit_menu(target=message, state=state)


@router.message(ProfileEdit.work_end, F.text)
async def edit_work_end(message: Message, state: FSMContext) -> None:
    if not await fields.apply_work_end(message=message, state=state):
        return
    await fields.show_edit_menu(target=message, state=state)


@router.callback_query(ProfileEdit.menu, EditSaveCB.filter())
async def save_edit(
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    profiles: UserProfileRepository,
    moderation: ModerationService,
    moderator_ids: frozenset[int],
) -> None:
    await fields.save_edits(
        callback=callback,
        state=state,
        bot=bot,
        profiles=profiles,
        moderation=moderation,
        moderator_ids=moderator_ids,
    )
