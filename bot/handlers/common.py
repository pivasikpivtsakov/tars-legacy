from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import render_menu, require_complete_profile
from bot.handlers.registration import begin_registration
from bot.keyboards.start import BackCB, OpenZoneCB, StartZone, back_kb
from common.repositories.user_profiles import (
    RankingStats,
    UserProfile,
    UserProfileRepository,
)

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await state.clear()
    if profile is None:
        await begin_registration(message=message, state=state)
        return
    await render_menu(target=message, profile=profile)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.ONLINE))
async def open_online(
    callback: CallbackQuery,
    profiles: UserProfileRepository,
    profile: UserProfile | None,
) -> None:
    if (await require_complete_profile(callback=callback, profile=profile)) is None:
        return
    profile = await profiles.toggle_is_online_and_get(user_id=callback.from_user.id)
    alert = (
        _("start.online_now_on") if profile.is_online else _("start.online_now_off")
    )
    await callback.answer(alert, show_alert=False)
    await render_menu(target=callback, profile=profile)


def _completion_rates(stats: RankingStats) -> tuple[int, int]:
    strict_total = stats.completed + stats.cancelled
    full_total = strict_total + stats.not_picked
    strict = round(stats.completed / strict_total * 100) if strict_total else 0
    full = round(stats.completed / full_total * 100) if full_total else 0
    return strict, full


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.PRIORITY))
async def open_priority(
    callback: CallbackQuery,
    profiles: UserProfileRepository,
    profile: UserProfile | None,
) -> None:
    stats = await profiles.ranking_stats(user_id=callback.from_user.id)
    rate_strict, rate_full = _completion_rates(stats)
    price = profile.price_60 if profile is not None and profile.price_60 is not None else 0
    speed = stats.speed_seconds if stats.speed_seconds is not None else "-"
    text = _("start.priority").format(
        speed=speed,
        price=price,
        rate_strict=rate_strict,
        rate_full=rate_full,
    )
    await callback.message.edit_text(
        text,
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.BALANCE))
async def open_balance(
    callback: CallbackQuery,
    profile: UserProfile | None,
) -> None:
    balance = profile.balance if profile is not None else 0
    await callback.message.edit_text(
        _("start.balance").format(balance=balance),
        reply_markup=back_kb(back_text=_("start.btn_back")),
    )
    await callback.answer()


@router.callback_query(BackCB.filter())
async def back_to_welcome(
    callback: CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await state.clear()
    await render_menu(target=callback, profile=profile)
    await callback.answer()
