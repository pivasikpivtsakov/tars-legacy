from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.handlers.menu import render_menu, require_complete_profile, show_back_panel
from bot.handlers.registration import begin_registration
from bot.keyboards.start import BackCB, OpenZoneCB, StartZone
from common.models.rating import RatingStats
from common.models.user_profiles import UserProfile
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository

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
    online_price_index: OnlinePriceIndex,
    profile: UserProfile | None,
) -> None:
    complete_profile = await require_complete_profile(callback=callback, profile=profile)
    if complete_profile is None:
        return
    profile = await profiles.toggle_is_online_and_get(profile_id=complete_profile.id)
    await online_price_index.sync(profile=profile)
    alert = (
        _("start.online_now_on") if profile.is_online else _("start.online_now_off")
    )
    await callback.answer(alert, show_alert=False)
    await render_menu(target=callback, profile=profile)


def _completion_rates(stats: RatingStats) -> tuple[int, int]:
    strict_total = stats.complete + stats.incomplete
    full_total = strict_total + stats.not_taken
    strict = round(stats.complete / strict_total * 100) if strict_total else 0
    full = round(stats.complete / full_total * 100) if full_total else 0
    return strict, full


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.PRIORITY))
async def open_priority(
    callback: CallbackQuery,
    rating: RatingRepository,
    profile: UserProfile | None,
) -> None:
    stats = (
        await rating.get(user_id=profile.id)
        if profile is not None
        else RatingStats(speed_seconds=None, complete=0, incomplete=0, not_taken=0)
    )
    rate_strict, rate_full = _completion_rates(stats)
    price = profile.price_60 if profile is not None and profile.price_60 is not None else 0
    speed = stats.speed_seconds if stats.speed_seconds is not None else "-"
    text = _("start.priority").format(
        speed=speed,
        price=price,
        rate_strict=rate_strict,
        rate_full=rate_full,
    )
    await show_back_panel(callback=callback, text=text)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.BALANCE))
async def open_balance(
    callback: CallbackQuery,
    profile: UserProfile | None,
) -> None:
    balance = profile.balance if profile is not None else 0
    await show_back_panel(
        callback=callback,
        text=_("start.balance").format(balance=balance),
    )


@router.callback_query(BackCB.filter())
async def back_to_welcome(
    callback: CallbackQuery,
    state: FSMContext,
    profile: UserProfile | None,
) -> None:
    await state.clear()
    await render_menu(target=callback, profile=profile)
    await callback.answer()
