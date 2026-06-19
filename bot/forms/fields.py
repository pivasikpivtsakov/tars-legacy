from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import datetime, time, timedelta, timezone
from typing import Any

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.forms.menu import MenuContext, render_menu
from bot.forms.states import STATE_BY_FIELD, ProfileEdit, Registration
from bot.keyboards.profile import (
    ProfileField,
    edit_menu_kb,
    packages_kb,
    with_codes_kb,
    works_alone_kb,
)
from common.models.user_profiles import UserProfile
from common.packages import PACKAGE_PRICE_LIMIT, format_prices
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import deactivate_and_notify

MSK_TZ = timezone(timedelta(hours=3))
TIME_FORMAT = "%H:%M"


def parse_msk_time(raw: str) -> time | None:
    try:
        parsed = datetime.strptime(raw.strip(), TIME_FORMAT).replace(tzinfo=MSK_TZ)
    except ValueError:
        return None
    return parsed.timetz()


def parse_price(raw: str, *, limit: int) -> int | None:
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    if value <= 0 or value > limit:
        return None
    return value


def _fmt_packages(packages: Sequence[int] | None) -> str:
    if not packages:
        return "-"
    return ", ".join(str(p) for p in packages)


def _fmt_time(value: time | None) -> str:
    if value is None:
        return "-"
    return value.strftime(TIME_FORMAT)


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return _("registration.btn_yes") if value else _("registration.btn_no")


def is_valid_work_hours(*, start: time, end: time) -> bool:
    return end > start


def packages_markup(selected: Iterable[int]) -> InlineKeyboardMarkup:
    return packages_kb(selected=selected, done_text=_("registration.btn_done"))


_TEXT_PROMPT_KEYS = {
    ProfileField.withdrawal_method: "registration.ask_withdrawal_method",
    ProfileField.work_start: "registration.ask_work_start",
    ProfileField.work_end: "registration.ask_work_end",
}


def field_prompt(
    field: ProfileField,
    *,
    selected: Iterable[int] = (),
) -> tuple[str, InlineKeyboardMarkup | None]:
    if field is ProfileField.works_alone:
        return _("registration.ask_works_alone"), works_alone_kb(
            yes_text=_("registration.btn_yes"),
            no_text=_("registration.btn_no"),
        )
    if field is ProfileField.with_codes:
        return _("registration.ask_with_codes"), with_codes_kb(
            yes_text=_("registration.btn_yes"),
            no_text=_("registration.btn_no"),
        )
    if field is ProfileField.packages:
        return _("registration.ask_packages"), packages_markup(selected)
    return _(_TEXT_PROMPT_KEYS[field]), None


async def send_prompt(
    message: Message,
    field: ProfileField,
    *,
    selected: Iterable[int] = (),
) -> None:
    text, markup = field_prompt(field, selected=selected)
    await message.answer(text, reply_markup=markup)


def _edit_labels() -> dict[ProfileField, str]:
    return {
        ProfileField.works_alone: _("edit.field_works_alone"),
        ProfileField.with_codes: _("edit.field_with_codes"),
        ProfileField.packages: _("edit.field_packages"),
        ProfileField.withdrawal_method: _("edit.field_withdrawal"),
        ProfileField.work_start: _("edit.field_work_start"),
        ProfileField.work_end: _("edit.field_work_end"),
    }


def _summary(template: str, data: Mapping[str, Any]) -> str:
    return template.format(
        works_alone=_fmt_bool(data["works_alone"]),
        with_codes=_fmt_bool(data["with_codes"]),
        packages=_fmt_packages(data["packages"]),
        prices=format_prices(data["prices"]),
        withdrawal_method=data["withdrawal_method"] or "-",
        work_start=_fmt_time(time.fromisoformat(data["work_start"])),
        work_end=_fmt_time(time.fromisoformat(data["work_end"])),
    )


def _profile_data(profile: UserProfile) -> dict[str, Any]:
    return {
        "works_alone": profile.works_alone,
        "with_codes": profile.with_codes,
        "packages": list(profile.packages or ()),
        "prices": {str(size): price for size, price in (profile.prices or {}).items()},
        "withdrawal_method": profile.withdrawal_method,
        "work_start": profile.work_start.isoformat() if profile.work_start else None,
        "work_end": profile.work_end.isoformat() if profile.work_end else None,
    }


async def apply_works_alone(*, state: FSMContext, value: bool) -> None:
    await state.update_data(works_alone=value)


async def apply_with_codes(*, state: FSMContext, value: bool) -> None:
    await state.update_data(with_codes=value)


async def apply_withdrawal(*, state: FSMContext, text: str) -> None:
    await state.update_data(withdrawal_method=text)


def _next_unpriced_size(data: Mapping[str, Any]) -> int | None:
    prices = data.get("prices") or {}
    for size in data.get("packages") or ():
        if str(size) not in prices:
            return size
    return None


async def begin_pricing(*, message: Message, state: FSMContext) -> None:
    await state.update_data(prices={})
    await prompt_next_pack_price(message=message, state=state)


async def prompt_next_pack_price(*, message: Message, state: FSMContext) -> bool:
    size = _next_unpriced_size(await state.get_data())
    if size is None:
        return False
    await message.answer(
        _("registration.ask_pack_price").format(
            size=size,
            limit=PACKAGE_PRICE_LIMIT[size],
        ),
    )
    return True


async def apply_pack_price(*, message: Message, state: FSMContext) -> bool:
    data = await state.get_data()
    size = _next_unpriced_size(data)
    if size is None:
        return True
    parsed = parse_price(message.text, limit=PACKAGE_PRICE_LIMIT[size])
    if parsed is None:
        await message.answer(
            _("registration.invalid_price").format(limit=PACKAGE_PRICE_LIMIT[size]),
        )
        return False
    prices = dict(data.get("prices") or {})
    prices[str(size)] = parsed
    await state.update_data(prices=prices)
    return True


async def _apply_work_time(
    *,
    message: Message,
    state: FSMContext,
    key: str,
    other_key: str,
    new_is_start: bool,
) -> bool:
    parsed = parse_msk_time(message.text)
    if parsed is None:
        await message.answer(_("registration.invalid_time"))
        return False
    other_iso = (await state.get_data()).get(other_key)
    if other_iso is not None:
        other = time.fromisoformat(other_iso)
        start, end = (parsed, other) if new_is_start else (other, parsed)
        if not is_valid_work_hours(start=start, end=end):
            await message.answer(_("registration.work_end_before_start"))
            return False
    await state.update_data({key: parsed.isoformat()})
    return True


async def apply_work_start(*, message: Message, state: FSMContext) -> bool:
    return await _apply_work_time(
        message=message,
        state=state,
        key="work_start",
        other_key="work_end",
        new_is_start=True,
    )


async def apply_work_end(*, message: Message, state: FSMContext) -> bool:
    return await _apply_work_time(
        message=message,
        state=state,
        key="work_end",
        other_key="work_start",
        new_is_start=False,
    )


def _toggle_packages(selected: Iterable[int], value: int) -> list[int]:
    result = set(selected)
    if value in result:
        result.discard(value)
    else:
        result.add(value)
    return sorted(result)


async def toggle_and_render(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    value: int,
) -> None:
    data = await state.get_data()
    selected = _toggle_packages(data.get("packages", []), value)
    await state.update_data(packages=selected)
    await callback.message.edit_reply_markup(reply_markup=packages_markup(selected))


async def ensure_packages_selected(
    *,
    callback: CallbackQuery,
    state: FSMContext,
) -> bool:
    data = await state.get_data()
    if data.get("packages"):
        return True
    await callback.answer(_("registration.no_packages_selected"), show_alert=True)
    return False


async def begin_registration(*, message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Registration.works_alone)
    await send_prompt(message, ProfileField.works_alone)


async def save_profile_from_data(
    *,
    tg_id: int,
    data: Mapping[str, Any],
    bot: Bot,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    moderator_ids: Collection[int],
) -> UserProfile:
    prices = {int(size): price for size, price in (data["prices"] or {}).items()}
    profile = await profiles.create_or_update(
        tg_id=tg_id,
        works_alone=data["works_alone"],
        with_codes=data["with_codes"],
        prices=prices,
        withdrawal_method=data["withdrawal_method"],
        work_start=time.fromisoformat(data["work_start"]),
        work_end=time.fromisoformat(data["work_end"]),
    )
    await deactivate_and_notify(
        bot=bot,
        moderator_ids=moderator_ids,
        profiles=profiles,
        online_price_index=online_price_index,
        profile=profile,
    )
    return profile


async def finish_registration(
    *,
    message: Message,
    state: FSMContext,
    bot: Bot,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    moderator_ids: Collection[int],
) -> None:
    data = await state.get_data()
    profile = await save_profile_from_data(
        tg_id=message.from_user.id,
        data=data,
        bot=bot,
        profiles=profiles,
        online_price_index=online_price_index,
        moderator_ids=moderator_ids,
    )
    await state.set_state(Registration.finished_filling)
    await message.answer(_summary(_("registration.done"), data))
    await render_menu(MenuContext(target=message, state=state, profile=profile))


async def load_profile_into_state(
    *,
    state: FSMContext,
    profile: UserProfile,
) -> None:
    await state.update_data(_profile_data(profile))


async def show_edit_menu(
    *,
    target: Message | CallbackQuery,
    state: FSMContext,
) -> None:
    await state.set_state(ProfileEdit.menu)
    data = await state.get_data()
    text = _summary(_("edit.title"), data)
    markup = edit_menu_kb(
        labels=_edit_labels(),
        save_text=_("edit.btn_save"),
        cancel_text=_("edit.btn_cancel"),
    )
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        return
    await target.answer(text, reply_markup=markup)


async def begin_field_edit(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    field: ProfileField,
) -> None:
    await state.set_state(STATE_BY_FIELD[field])
    data = await state.get_data()
    text, markup = field_prompt(field, selected=data["packages"])
    await callback.message.edit_text(text, reply_markup=markup)


async def save_edits(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    moderator_ids: Collection[int],
) -> None:
    updated = await save_profile_from_data(
        tg_id=callback.from_user.id,
        data=await state.get_data(),
        bot=bot,
        profiles=profiles,
        online_price_index=online_price_index,
        moderator_ids=moderator_ids,
    )
    await state.clear()
    await render_menu(MenuContext(target=callback, state=state, profile=updated))
    await callback.answer(_("edit.saved"))
