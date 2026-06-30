from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Any

from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.forms.menu import MenuContext, render_menu
from bot.forms.states import (
    PRICES_STATE_BY_PACKAGES,
    STATE_BY_FIELD,
    ProfileEdit,
    Registration,
)
from bot.keyboards.profile import (
    ProfileField,
    chat_addable_kb,
    edit_menu_kb,
    pack_price_kb,
    packages_grid_kb,
    with_codes_kb,
)
from bot.utils.telegram import ignore_message_gone
from common.catalog.packages import format_prices, format_prices_table
from common.catalog.tiers import PACK_TIERS, TierNumber
from common.models.user_profiles import UserProfile
from common.money import format_money, parse_money
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.pack_price_limits import PackPriceLimitRepository
from common.services.moderation import ModerationService

_PACK_MSG_KEY = "pack_msg_id"
_SELECTED_KEY = "selected"
_PRICE_QUEUE_KEY = "price_queue"

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


def parse_price(raw: str, *, limit: Decimal) -> Decimal | PriceRejection:
    value = parse_money(raw)
    if value is None:
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
    if field is ProfileField.chat_addable:
        return _("registration.ask_chat_addable"), chat_addable_kb(
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


def _edit_labels(*, with_codes: bool) -> dict[ProfileField, str]:
    labels = {ProfileField.chat_addable: _("edit.field_chat_addable")}
    if not with_codes:
        labels[ProfileField.packages] = _("edit.field_packages")
    labels[ProfileField.withdrawal_method] = _("edit.field_withdrawal")
    labels[ProfileField.work_start] = _("edit.field_work_start")
    labels[ProfileField.work_end] = _("edit.field_work_end")
    return labels


def _prices_map(data: Mapping[str, Any]) -> dict[int, Decimal]:
    return {int(size): Decimal(str(price)) for size, price in (data.get("prices") or {}).items()}


def _store_prices(prices: Mapping[int, Decimal]) -> dict[str, str]:
    return {str(size): str(price) for size, price in prices.items()}


def _selected_set(data: Mapping[str, Any]) -> set[int]:
    return {int(size) for size in (data.get(_SELECTED_KEY) or [])}


def _summary(*, pack_key: str, code_key: str, data: Mapping[str, Any]) -> str:
    with_codes = data["with_codes"]
    common = {
        "chat_addable": _fmt_bool(data["chat_addable"]),
        "with_codes": _fmt_bool(with_codes),
        "withdrawal_method": data["withdrawal_method"] or "-",
        "work_start": _fmt_time(_iso_to_time(data.get("work_start"))),
        "work_end": _fmt_time(_iso_to_time(data.get("work_end"))),
    }
    if with_codes:
        return _(code_key).format(**common)
    prices = _prices_map(data)
    return _(pack_key).format(
        packages=_fmt_packages(sorted(prices)),
        prices=format_prices(prices),
        **common,
    )


def _profile_data(profile: UserProfile) -> dict[str, Any]:
    return {
        "chat_addable": profile.chat_addable,
        "with_codes": profile.with_codes,
        "tier": int(profile.tier),
        "prices": {str(size): str(price) for size, price in (profile.prices or {}).items()},
        "withdrawal_method": profile.withdrawal_method,
        "work_start": profile.work_start.isoformat() if profile.work_start else None,
        "work_end": profile.work_end.isoformat() if profile.work_end else None,
    }


def _package_above_tier_message(tier: int) -> str:
    pack_tier = PACK_TIERS.tier(TierNumber(tier))
    return _("registration.package_above_tier").format(
        tier=pack_tier.name(),
        max_package=max(pack_tier.allowed_packs()),
    )


async def apply_chat_addable(*, state: FSMContext, value: bool) -> None:
    await state.update_data(chat_addable=value)


async def apply_with_codes(*, state: FSMContext, value: bool) -> None:
    await state.update_data(with_codes=value)


async def apply_withdrawal(*, state: FSMContext, text: str) -> None:
    await state.update_data(withdrawal_method=text)


def _packages_text(
    *,
    selected: Collection[int],
    prices: Mapping[int, Decimal],
    tier: int | None,
) -> str:
    parts = [_("registration.ask_packages")]
    known = {size: prices[size] for size in sorted(selected) if size in prices}
    if known:
        parts.append(_("registration.your_packs").format(prices=format_prices_table(known)))
    if tier is not None:
        parts.append(_package_above_tier_message(tier))
    return "\n\n".join(parts)


def _packages_markup(selected: Collection[int]) -> InlineKeyboardMarkup:
    return packages_grid_kb(selected=sorted(selected), done_text=_("registration.btn_done"))


async def _render_grid(*, target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = _selected_set(data)
    text = _packages_text(selected=selected, prices=_prices_map(data), tier=data.get("tier"))
    markup = _packages_markup(selected)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        message_id = target.message.message_id
    else:
        sent = await target.answer(text, reply_markup=markup)
        message_id = sent.message_id
    await state.update_data({_PACK_MSG_KEY: message_id})


async def show_packages_grid(*, target: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data({_SELECTED_KEY: sorted(_prices_map(data))})
    await _render_grid(target=target, state=state)


async def toggle_pack(*, callback: CallbackQuery, state: FSMContext, value: int) -> None:
    data = await state.get_data()
    selected = _selected_set(data)
    tier = data.get("tier")
    if (
        value not in selected
        and tier is not None
        and value not in PACK_TIERS.tier(TierNumber(tier)).allowed_packs()
    ):
        await callback.answer(_package_above_tier_message(tier), show_alert=True)
        return
    if value in selected:
        selected.discard(value)
    else:
        selected.add(value)
    await state.update_data({_SELECTED_KEY: sorted(selected)})
    await _render_grid(target=callback, state=state)


async def cancel_pack(*, callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data({_PRICE_QUEUE_KEY: []})
    await _render_grid(target=callback, state=state)


async def ensure_packages_selected(
    *,
    callback: CallbackQuery,
    state: FSMContext,
) -> bool:
    data = await state.get_data()
    selected = _selected_set(data)
    if not selected:
        await callback.answer(_("registration.no_packages_selected"), show_alert=True)
        return False
    tier = data.get("tier")
    if tier is not None:
        allowed = set(PACK_TIERS.tier(TierNumber(tier)).allowed_packs())
        if any(size not in allowed for size in selected):
            await callback.answer(_package_above_tier_message(tier), show_alert=True)
            return False
    return True


async def start_price_entry(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    await state.set_state(PRICES_STATE_BY_PACKAGES[await state.get_state()])
    data = await state.get_data()
    queue = sorted(_selected_set(data))
    await state.update_data(
        {_PRICE_QUEUE_KEY: queue, _PACK_MSG_KEY: callback.message.message_id},
    )
    await _prompt_next_price(
        message=callback.message,
        state=state,
        pack_price_limits=pack_price_limits,
    )


async def _prompt_next_price(
    *,
    message: Message,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    data = await state.get_data()
    size = int(data[_PRICE_QUEUE_KEY][0])
    limit = await pack_price_limits.get(size=size)
    prev = _prices_map(data).get(size)
    text = _("registration.ask_pack_price").format(
        size=size,
        prev=format_money(prev) if prev is not None else "-",
        limit=format_money(limit),
    )
    await _replace_pack_message(message=message, state=state, text=text)


async def _replace_pack_message(
    *,
    message: Message,
    state: FSMContext,
    text: str,
) -> None:
    old_message_id = (await state.get_data()).get(_PACK_MSG_KEY)
    if old_message_id is not None:
        with ignore_message_gone():
            await message.bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    sent = await message.answer(
        text,
        reply_markup=pack_price_kb(cancel_text=_("registration.btn_cancel_pack")),
    )
    await state.update_data({_PACK_MSG_KEY: sent.message_id})


async def submit_pack_price(
    *,
    message: Message,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> bool:
    data = await state.get_data()
    queue = [int(size) for size in (data.get(_PRICE_QUEUE_KEY) or [])]
    if not queue:
        return False
    size = queue[0]
    limit = await pack_price_limits.get(size=size)
    parsed = parse_price(message.text, limit=limit)
    if isinstance(parsed, PriceRejection):
        rejection_key = (
            "registration.price_too_high"
            if parsed is PriceRejection.OUT_OF_RANGE
            else "registration.invalid_price"
        )
        await message.answer(_(rejection_key).format(size=size, limit=format_money(limit)))
        return False
    prices = _prices_map(data)
    prices[size] = parsed
    remaining = queue[1:]
    if remaining:
        await state.update_data(
            {"prices": _store_prices(prices), _PRICE_QUEUE_KEY: remaining},
        )
        await _prompt_next_price(
            message=message,
            state=state,
            pack_price_limits=pack_price_limits,
        )
        return False
    selected = _selected_set(data)
    pruned = {pack: prices[pack] for pack in sorted(selected) if pack in prices}
    old_message_id = data.get(_PACK_MSG_KEY)
    if old_message_id is not None:
        with ignore_message_gone():
            await message.bot.delete_message(chat_id=message.chat.id, message_id=old_message_id)
    await state.update_data(
        {"prices": _store_prices(pruned), _PRICE_QUEUE_KEY: [], _PACK_MSG_KEY: None},
    )
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


async def begin_registration(*, message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Registration.chat_addable)
    await send_prompt(message, ProfileField.chat_addable)


async def save_profile_from_data(
    *,
    tg_id: int,
    data: Mapping[str, Any],
    bot: Bot,
    profiles: UserProfileRepository,
    moderation: ModerationService,
    moderator_ids: Collection[int],
) -> UserProfile:
    with_codes = data["with_codes"]
    prices = (
        {}
        if with_codes
        else {int(size): Decimal(str(price)) for size, price in (data.get("prices") or {}).items()}
    )
    profile = await profiles.create_or_update(
        tg_id=tg_id,
        chat_addable=data["chat_addable"],
        with_codes=with_codes,
        prices=prices,
        withdrawal_method=data["withdrawal_method"],
        work_start=time.fromisoformat(data["work_start"]),
        work_end=time.fromisoformat(data["work_end"]),
    )
    await moderation.deactivate_and_notify(
        bot=bot,
        moderator_ids=moderator_ids,
        profile=profile,
    )
    return profile


async def finish_registration(
    *,
    message: Message,
    state: FSMContext,
    bot: Bot,
    profiles: UserProfileRepository,
    moderation: ModerationService,
    moderator_ids: Collection[int],
) -> None:
    data = await state.get_data()
    profile = await save_profile_from_data(
        tg_id=message.from_user.id,
        data=data,
        bot=bot,
        profiles=profiles,
        moderation=moderation,
        moderator_ids=moderator_ids,
    )
    await state.set_state(Registration.finished_filling)
    await message.answer(
        _summary(pack_key="registration.done", code_key="registration.done_codes", data=data),
    )
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
    text = _summary(pack_key="edit.title", code_key="edit.title_codes", data=data)
    markup = edit_menu_kb(
        labels=_edit_labels(with_codes=data["with_codes"]),
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
    moderation: ModerationService,
    moderator_ids: Collection[int],
) -> None:
    updated = await save_profile_from_data(
        tg_id=callback.from_user.id,
        data=await state.get_data(),
        bot=bot,
        profiles=profiles,
        moderation=moderation,
        moderator_ids=moderator_ids,
    )
    await state.clear()
    await render_menu(MenuContext(target=callback, state=state, profile=updated))
    await callback.answer(_("edit.saved"))
