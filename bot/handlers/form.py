from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.i18n import gettext as _

from bot.storage.user_profiles import UserProfileRepository

router = Router(name="form")


class Form(StatesGroup):
    name = State()
    language = State()
    finished_filling = State()


@router.message(Command("form"))
async def cmd_form(message: Message, state: FSMContext) -> None:
    await state.set_state(Form.name)
    await message.answer(_("form.ask_name"))


@router.message(Command("restart"))
@router.message(F.text.casefold() == "restart")
async def cmd_restart(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer(_("form.nothing_to_restart"))
        return
    await state.clear()
    await message.answer(_("form.restarted"))


@router.message(Form.name, F.text)
async def process_name(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    await profiles.set_name(user_id=message.from_user.id, name=message.text)
    await state.set_state(Form.language)
    await message.answer(_("form.ask_language").format(name=message.text))


@router.message(Form.language, F.text)
async def process_language(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    profile = await profiles.set_language(
        user_id=message.from_user.id,
        language=message.text,
    )
    await state.set_state(Form.finished_filling)
    await message.answer(
        _("form.done").format(name=profile.name, language=profile.language),
    )


@router.message(Form.finished_filling)
async def process_finished_filling(
    message: Message,
    state: FSMContext,  # noqa: ARG001
) -> None:
    await message.answer(_("form.finished_filling"))
