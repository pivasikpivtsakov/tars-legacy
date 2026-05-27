from datetime import datetime, time, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.keyboards import (
    PackagesDoneCB,
    PackageToggleCB,
    WorksAloneCB,
    packages_kb,
    works_alone_kb,
)
from bot.storage.user_profiles import UserProfile, UserProfileRepository

router = Router(name="form")

MSK_TZ = timezone(timedelta(hours=3))
_TIME_FORMAT = "%H:%M"


class Form(StatesGroup):
    works_alone = State()
    packages = State()
    withdrawal_method = State()
    work_start = State()
    work_end = State()
    finished_filling = State()


def _parse_msk_time(raw: str) -> time | None:
    try:
        parsed = datetime.strptime(raw.strip(), _TIME_FORMAT).time()
    except ValueError:
        return None
    return parsed.replace(tzinfo=MSK_TZ)


def _fmt_packages(packages: tuple[int, ...] | None) -> str:
    if not packages:
        return "-"
    return ", ".join(str(p) for p in packages)


def _fmt_time(t: time | None) -> str:
    if t is None:
        return "-"
    return t.strftime(_TIME_FORMAT)


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return _("form.btn_yes") if value else _("form.btn_no")


def _render_summary(profile: UserProfile) -> str:
    return _("form.done").format(
        works_alone=_fmt_bool(profile.works_alone),
        packages=_fmt_packages(profile.packages),
        withdrawal_method=profile.withdrawal_method or "-",
        work_start=_fmt_time(profile.work_start),
        work_end=_fmt_time(profile.work_end),
    )


@router.message(Command("form"))
async def cmd_form(message: Message, state: FSMContext) -> None:
    await state.set_state(Form.works_alone)
    await state.update_data(packages=[])
    await message.answer(
        _("form.ask_works_alone"),
        reply_markup=works_alone_kb(
            yes_text=_("form.btn_yes"),
            no_text=_("form.btn_no"),
        ),
    )


@router.message(Command("restart"))
@router.message(F.text.casefold() == "restart")
async def cmd_restart(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer(_("form.nothing_to_restart"))
        return
    await state.clear()
    await message.answer(_("form.restarted"))


@router.callback_query(Form.works_alone, WorksAloneCB.filter())
async def process_works_alone(
    callback: CallbackQuery,
    callback_data: WorksAloneCB,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    await profiles.set_works_alone(
        user_id=callback.from_user.id,
        works_alone=callback_data.value,
    )
    await state.set_state(Form.packages)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        _("form.ask_packages"),
        reply_markup=packages_kb(selected=set(), done_text=_("form.btn_done")),
    )
    await callback.answer()


@router.callback_query(Form.packages, PackageToggleCB.filter())
async def process_package_toggle(
    callback: CallbackQuery,
    callback_data: PackageToggleCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    selected: set[int] = set(data["packages"])
    if callback_data.value in selected:
        selected.remove(callback_data.value)
    else:
        selected.add(callback_data.value)
    await state.update_data(packages=sorted(selected))
    await callback.message.edit_reply_markup(
        reply_markup=packages_kb(selected=selected, done_text=_("form.btn_done")),
    )
    await callback.answer()


@router.callback_query(Form.packages, PackagesDoneCB.filter())
async def process_packages_done(
    callback: CallbackQuery,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    data = await state.get_data()
    selected: list[int] = sorted(set(data["packages"]))
    if not selected:
        await callback.answer(_("form.no_packages_selected"), show_alert=True)
        return
    await profiles.set_packages(user_id=callback.from_user.id, packages=selected)
    await state.set_state(Form.withdrawal_method)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(_("form.ask_withdrawal_method"))
    await callback.answer()


@router.message(Form.withdrawal_method, F.text)
async def process_withdrawal_method(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    await profiles.set_withdrawal_method(
        user_id=message.from_user.id,
        withdrawal_method=message.text,
    )
    await state.set_state(Form.work_start)
    await message.answer(_("form.ask_work_start"))


@router.message(Form.work_start, F.text)
async def process_work_start(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    parsed = _parse_msk_time(message.text)
    if parsed is None:
        await message.answer(_("form.invalid_time"))
        return
    await profiles.set_work_start(user_id=message.from_user.id, work_start=parsed)
    await state.update_data(work_start=parsed.strftime(_TIME_FORMAT))
    await state.set_state(Form.work_end)
    await message.answer(_("form.ask_work_end"))


@router.message(Form.work_end, F.text)
async def process_work_end(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    parsed = _parse_msk_time(message.text)
    if parsed is None:
        await message.answer(_("form.invalid_time"))
        return
    data = await state.get_data()
    start_raw = data["work_start"]
    start = datetime.strptime(start_raw, _TIME_FORMAT).time().replace(tzinfo=MSK_TZ)
    if parsed <= start:
        await message.answer(_("form.work_end_before_start"))
        return
    profile = await profiles.set_work_end_and_get(
        user_id=message.from_user.id,
        work_end=parsed,
    )
    await state.set_state(Form.finished_filling)
    await message.answer(_render_summary(profile))


@router.message(Form.finished_filling)
async def process_finished_filling(message: Message, state: FSMContext) -> None:
    await message.answer(_("form.finished_filling"))
