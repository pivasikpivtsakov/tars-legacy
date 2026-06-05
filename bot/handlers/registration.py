from datetime import datetime, time, timedelta, timezone

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import menu_button_markup, render_menu
from bot.handlers.moderation import MODERATOR_NOT_ORDER_TAKER
from bot.keyboards._packages import PackageToggleCB
from bot.keyboards.registration import (
    PackagesDoneCB,
    WorksAloneCB,
    packages_kb,
    works_alone_kb,
)
from bot.keyboards.start import OpenZoneCB, StartZone
from common.models.user_profiles import UserProfile
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import deactivate_and_notify, is_moderator

router = Router(name="registration")

MSK_TZ = timezone(timedelta(hours=3))
_TIME_FORMAT = "%H:%M"
_MAX_PRICE = 1_000


class Registration(StatesGroup):
    works_alone = State()
    packages = State()
    price_60 = State()
    withdrawal_method = State()
    work_start = State()
    work_end = State()
    finished_filling = State()


def _parse_msk_time(raw: str) -> time | None:
    try:
        parsed = datetime.strptime(raw.strip(), _TIME_FORMAT).replace(tzinfo=MSK_TZ)
    except ValueError:
        return None
    return parsed.timetz()


def _parse_price(raw: str) -> int | None:
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    if value <= 0 or value > _MAX_PRICE:
        return None
    return value


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
    return _("registration.btn_yes") if value else _("registration.btn_no")


def _fmt_price(value: int | None) -> str:
    if value is None:
        return "-"
    return str(value)


def _render_summary(profile: UserProfile) -> str:
    return _("registration.done").format(
        works_alone=_fmt_bool(profile.works_alone),
        packages=_fmt_packages(profile.packages),
        price_60=_fmt_price(profile.price_60),
        withdrawal_method=profile.withdrawal_method or "-",
        work_start=_fmt_time(profile.work_start),
        work_end=_fmt_time(profile.work_end),
    )


async def begin_registration(*, message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Registration.works_alone)
    await message.answer(
        _("registration.ask_works_alone"),
        reply_markup=works_alone_kb(
            yes_text=_("registration.btn_yes"),
            no_text=_("registration.btn_no"),
        ),
    )


@router.message(Command("register"))
async def cmd_register(
    message: Message,
    state: FSMContext,
    moderator_ids: frozenset[int],
    profiles: UserProfileRepository,
) -> None:
    if await is_moderator(
        profiles=profiles,
        moderator_ids=moderator_ids,
        tg_id=message.from_user.id,
    ):
        await message.answer(MODERATOR_NOT_ORDER_TAKER)
        return
    await begin_registration(message=message, state=state)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.REGISTER))
async def open_register(
    callback: CallbackQuery,
    state: FSMContext,
    moderator_ids: frozenset[int],
    profiles: UserProfileRepository,
) -> None:
    if await is_moderator(
        profiles=profiles,
        moderator_ids=moderator_ids,
        tg_id=callback.from_user.id,
    ):
        await callback.answer(MODERATOR_NOT_ORDER_TAKER, show_alert=True)
        return
    await callback.message.edit_reply_markup(reply_markup=None)
    await begin_registration(message=callback.message, state=state)
    await callback.answer()


@router.message(Command("restart"))
@router.message(F.text.casefold() == "restart")
async def cmd_restart(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is None:
        await message.answer(_("registration.nothing_to_restart"))
        return
    await state.clear()
    await message.answer(_("registration.restarted"))


@router.callback_query(Registration.works_alone, WorksAloneCB.filter())
async def process_works_alone(
    callback: CallbackQuery,
    callback_data: WorksAloneCB,
    state: FSMContext,
) -> None:
    await state.update_data(works_alone=callback_data.value)
    await state.set_state(Registration.packages)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        _("registration.ask_packages"),
        reply_markup=packages_kb(
            selected=(),
            done_text=_("registration.btn_done"),
        ),
    )
    await callback.answer()


@router.callback_query(Registration.packages, PackageToggleCB.filter())
async def process_package_toggle(
    callback: CallbackQuery,
    callback_data: PackageToggleCB,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    selected = set(data.get("packages", []))
    if callback_data.value in selected:
        selected.remove(callback_data.value)
    else:
        selected.add(callback_data.value)
    await state.update_data(packages=sorted(selected))
    await callback.message.edit_reply_markup(
        reply_markup=packages_kb(
            selected=selected,
            done_text=_("registration.btn_done"),
        ),
    )
    await callback.answer()


@router.callback_query(Registration.packages, PackagesDoneCB.filter())
async def process_packages_done(
    callback: CallbackQuery,
    state: FSMContext,
) -> None:
    data = await state.get_data()
    if not data.get("packages"):
        await callback.answer(
            _("registration.no_packages_selected"),
            show_alert=True,
        )
        return
    await state.set_state(Registration.price_60)
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(_("registration.ask_price"))
    await callback.answer()


@router.message(Registration.price_60, F.text)
async def process_price(
    message: Message,
    state: FSMContext,
) -> None:
    parsed = _parse_price(message.text)
    if parsed is None:
        await message.answer(_("registration.invalid_price"))
        return
    await state.update_data(price_60=parsed)
    await state.set_state(Registration.withdrawal_method)
    await message.answer(_("registration.ask_withdrawal_method"))


@router.message(Registration.withdrawal_method, F.text)
async def process_withdrawal_method(
    message: Message,
    state: FSMContext,
) -> None:
    await state.update_data(withdrawal_method=message.text)
    await state.set_state(Registration.work_start)
    await message.answer(_("registration.ask_work_start"))


@router.message(Registration.work_start, F.text)
async def process_work_start(
    message: Message,
    state: FSMContext,
) -> None:
    parsed = _parse_msk_time(message.text)
    if parsed is None:
        await message.answer(_("registration.invalid_time"))
        return
    await state.update_data(work_start=parsed.isoformat())
    await state.set_state(Registration.work_end)
    await message.answer(_("registration.ask_work_end"))


@router.message(Registration.work_end, F.text)
async def process_work_end(
    message: Message,
    state: FSMContext,
    bot: Bot,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    moderator_ids: frozenset[int],
) -> None:
    parsed = _parse_msk_time(message.text)
    if parsed is None:
        await message.answer(_("registration.invalid_time"))
        return
    data = await state.get_data()
    work_start_iso = data.get("work_start")
    if work_start_iso is None:
        await state.set_state(Registration.work_start)
        await message.answer(_("registration.ask_work_start"))
        return
    work_start = time.fromisoformat(work_start_iso)
    if parsed <= work_start:
        await message.answer(_("registration.work_end_before_start"))
        return
    profile = await profiles.create_or_update(
        tg_id=message.from_user.id,
        works_alone=data["works_alone"],
        packages=data["packages"],
        price_60=data["price_60"],
        withdrawal_method=data["withdrawal_method"],
        work_start=work_start,
        work_end=parsed,
    )
    await deactivate_and_notify(
        bot=bot,
        moderator_ids=moderator_ids,
        profiles=profiles,
        online_price_index=online_price_index,
        profile=profile,
    )
    await state.set_state(Registration.finished_filling)
    await message.answer(_render_summary(profile), reply_markup=menu_button_markup())
    await render_menu(target=message, profile=profile)


@router.message(Registration.finished_filling)
async def process_finished_filling(message: Message) -> None:
    await message.answer(_("registration.finished_filling"))
