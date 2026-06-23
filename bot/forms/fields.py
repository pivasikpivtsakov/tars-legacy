from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, time, timedelta, timezone
from enum import StrEnum
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
    pack_confirm_kb,
    pack_manage_kb,
    pack_price_kb,
    packages_grid_kb,
    with_codes_kb,
    works_alone_kb,
)
from bot.utils.telegram import ignore_message_gone
from common.catalog.packages import format_prices, format_prices_table
from common.catalog.tiers import (
    TIER_MAX_AMOUNT,
    Tier,
    allowed_packages_for_tier,
    max_package_for_tier,
)
from common.models.user_profiles import UserProfile
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.pack_price_limits import PackPriceLimitRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import deactivate_and_notify

_PACK_MSG_KEY = "pack_msg_id"
_PRICING_SIZE_KEY = "pricing_size"

MSK_TZ = timezone(timedelta(hours=3))
TIME_FORMAT = "%H:%M"


def parse_msk_time(raw: str) -> time | None:
    try:
        parsed = datetime.strptime(raw.strip(), TIME_FORMAT).replace(tzinfo=MSK_TZ)
    except ValueError:
        return None
    return parsed.timetz()


class PriceRejection(StrEnum):
    NOT_A_NUMBER = "not_a_number"
    OUT_OF_RANGE = "out_of_range"


def parse_price(raw: str, *, limit: int) -> int | PriceRejection:
    try:
        value = int(raw.strip())
    except ValueError:
        return PriceRejection.NOT_A_NUMBER
    if value <= 0 or value > limit:
        return PriceRejection.OUT_OF_RANGE
    return value


def _fmt_packages(packages: Sequence[int] | None) -> str:
    if not packages:
        return "-"
    return ", ".join(str(p) for p in packages)


def _fmt_time(value: time | None) -> str:
    if value is None:
        return "-"
    return value.strftime(TIME_FORMAT)


def _iso_to_time(value: str | None) -> time | None:
    return time.fromisoformat(value) if value else None


def _fmt_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return _("registration.btn_yes") if value else _("registration.btn_no")


def is_valid_work_hours(*, start: time, end: time) -> bool:
    return end > start


_TEXT_PROMPT_KEYS = {
    ProfileField.withdrawal_method: "registration.ask_withdrawal_method",
    ProfileField.work_start: "registration.ask_work_start",
    ProfileField.work_end: "registration.ask_work_end",
}


def field_prompt(field: ProfileField) -> tuple[str, InlineKeyboardMarkup | None]:
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
    return _(_TEXT_PROMPT_KEYS[field]), None


async def send_prompt(message: Message, field: ProfileField) -> None:
    text, markup = field_prompt(field)
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


def _prices_map(data: Mapping[str, Any]) -> dict[int, int]:
    return {int(size): int(price) for size, price in (data.get("prices") or {}).items()}


def _store_prices(prices: Mapping[int, int]) -> dict[str, int]:
    return {str(size): price for size, price in prices.items()}


def _summary(template: str, data: Mapping[str, Any]) -> str:
    prices = _prices_map(data)
    return template.format(
        works_alone=_fmt_bool(data["works_alone"]),
        with_codes=_fmt_bool(data["with_codes"]),
        packages=_fmt_packages(sorted(prices)),
        prices=format_prices(prices),
        withdrawal_method=data["withdrawal_method"] or "-",
        work_start=_fmt_time(_iso_to_time(data.get("work_start"))),
        work_end=_fmt_time(_iso_to_time(data.get("work_end"))),
    )


def _profile_data(profile: UserProfile) -> dict[str, Any]:
    return {
        "works_alone": profile.works_alone,
        "with_codes": profile.with_codes,
        "tier": int(profile.tier),
        "prices": {str(size): price for size, price in (profile.prices or {}).items()},
        "withdrawal_method": profile.withdrawal_method,
        "work_start": profile.work_start.isoformat() if profile.work_start else None,
        "work_end": profile.work_end.isoformat() if profile.work_end else None,
    }


def _package_above_tier_message(tier: int) -> str:
    return _("registration.package_above_tier").format(
        cap=TIER_MAX_AMOUNT[Tier(tier)],
        max_package=max_package_for_tier(Tier(tier)),
    )


async def apply_works_alone(*, state: FSMContext, value: bool) -> None:
    await state.update_data(works_alone=value)


async def apply_with_codes(*, state: FSMContext, value: bool) -> None:
    await state.update_data(with_codes=value)


async def apply_withdrawal(*, state: FSMContext, text: str) -> None:
    await state.update_data(withdrawal_method=text)


def _packages_text(*, prices: Mapping[int, int], tier: int | None) -> str:
    parts = [_("registration.ask_packages")]
    if prices:
        parts.append(_("registration.your_packs").format(prices=format_prices_table(prices)))
    if tier is not None:
        parts.append(_package_above_tier_message(tier))
    return "\n\n".join(parts)


def _packages_markup(prices: Mapping[int, int]) -> InlineKeyboardMarkup:
    return packages_grid_kb(selected=sorted(prices), done_text=_("registration.btn_done"))


async def show_packages_grid(*, target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    prices = _prices_map(data)
    text = _packages_text(prices=prices, tier=data.get("tier"))
    markup = _packages_markup(prices)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        message_id = target.message.message_id
    else:
        sent = await target.answer(text, reply_markup=markup)
        message_id = sent.message_id
    await state.update_data({_PACK_MSG_KEY: message_id, _PRICING_SIZE_KEY: None})


async def open_pack_panel(*, callback: CallbackQuery, state: FSMContext, value: int) -> None:
    data = await state.get_data()
    prices = _prices_map(data)
    tier = data.get("tier")
    if (
        value not in prices
        and tier is not None
        and value not in allowed_packages_for_tier(Tier(tier))
    ):
        await callback.answer(_package_above_tier_message(tier), show_alert=True)
        return
    if value in prices:
        text = _("registration.pack_manage").format(size=value, price=prices[value])
        markup = pack_manage_kb(
            value=value,
            change_text=_("registration.btn_change_price"),
            remove_text=_("registration.btn_remove_pack"),
            cancel_text=_("registration.btn_cancel_pack"),
        )
    else:
        text = _("registration.pack_confirm").format(size=value)
        markup = pack_confirm_kb(
            value=value,
            yes_text=_("registration.btn_set_price"),
            cancel_text=_("registration.btn_cancel_pack"),
        )
    await callback.message.edit_text(text, reply_markup=markup)


async def prompt_pack_price(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    value: int,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    await state.update_data(
        {_PRICING_SIZE_KEY: value, _PACK_MSG_KEY: callback.message.message_id},
    )
    limit = await pack_price_limits.get(size=value)
    await callback.message.edit_text(
        _("registration.ask_pack_price").format(size=value, limit=limit),
        reply_markup=pack_price_kb(cancel_text=_("registration.btn_cancel_pack")),
    )


async def remove_pack(*, callback: CallbackQuery, state: FSMContext, value: int) -> None:
    data = await state.get_data()
    prices = _prices_map(data)
    prices.pop(value, None)
    await state.update_data(prices=_store_prices(prices))
    await show_packages_grid(target=callback, state=state)


async def cancel_pack(*, callback: CallbackQuery, state: FSMContext) -> None:
    await show_packages_grid(target=callback, state=state)


async def apply_pack_price(
    *,
    message: Message,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> bool:
    data = await state.get_data()
    size = data.get(_PRICING_SIZE_KEY)
    if size is None:
        return False
    limit = await pack_price_limits.get(size=size)
    parsed = parse_price(message.text, limit=limit)
    if isinstance(parsed, PriceRejection):
        rejection_key = (
            "registration.price_too_high"
            if parsed is PriceRejection.OUT_OF_RANGE
            else "registration.invalid_price"
        )
        await message.answer(_(rejection_key).format(size=size, limit=limit))
        return False
    prices = _prices_map(data)
    prices[size] = parsed
    await state.update_data(prices=_store_prices(prices), **{_PRICING_SIZE_KEY: None})
    await _rerender_packages_grid(message=message, state=state)
    return True


async def _rerender_packages_grid(*, message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    prices = _prices_map(data)
    text = _packages_text(prices=prices, tier=data.get("tier"))
    markup = _packages_markup(prices)
    old_message_id = data.get(_PACK_MSG_KEY)
    if old_message_id is not None:
        with ignore_message_gone():
            await message.bot.delete_message(
                chat_id=message.chat.id,
                message_id=old_message_id,
            )
    sent = await message.answer(text, reply_markup=markup)
    await state.update_data({_PACK_MSG_KEY: sent.message_id})


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


async def ensure_packages_selected(
    *,
    callback: CallbackQuery,
    state: FSMContext,
) -> bool:
    data = await state.get_data()
    prices = _prices_map(data)
    if not prices:
        await callback.answer(_("registration.no_packages_selected"), show_alert=True)
        return False
    tier = data.get("tier")
    if tier is not None:
        allowed = set(allowed_packages_for_tier(Tier(tier)))
        if any(size not in allowed for size in prices):
            await callback.answer(_package_above_tier_message(tier), show_alert=True)
            return False
    return True


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
    if field is ProfileField.packages:
        await show_packages_grid(target=callback, state=state)
        return
    text, markup = field_prompt(field)
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
