from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from bot.forms import fields
from bot.forms.menu import (
    build_menu_context,
    install_menu_button,
    menu_available,
    open_menu,
    render_menu,
    show_back_panel,
)
from bot.keyboards.start import BackCB, OpenZoneCB, StartZone
from bot.middlewares.profile import require_active_profile
from common.catalog.packages import format_prices_table
from common.models.rating import RatingStats
from common.models.user_profiles import UserProfile
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.rating import RatingRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.bot_switch import BotSwitchService

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    profile: UserProfile | None,
    moderator_ids: frozenset[int],
    admin_ids: frozenset[int],
    bot_switch: BotSwitchService,
) -> None:
    await state.clear()
    if profile is None:
        await fields.begin_registration(message=message, state=state)
        return
    if menu_available(profile):
        await install_menu_button(message=message)
    context = await build_menu_context(
        target=message,
        state=state,
        profile=profile,
        admin_ids=admin_ids,
        moderator_ids=moderator_ids,
        bot_switch=bot_switch,
    )
    await render_menu(context)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.ONLINE))
@require_active_profile
async def open_online(
    callback: CallbackQuery,
    state: FSMContext,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
    profile: UserProfile,
    admin_ids: frozenset[int],
    moderator_ids: frozenset[int],
    bot_switch: BotSwitchService,
) -> None:
    profile = await profiles.toggle_is_online_and_get(profile_id=profile.id)
    await online_price_index.sync(profile=profile)
    alert = _("start.online_now_on") if profile.is_online else _("start.online_now_off")
    await callback.answer(alert, show_alert=False)
    context = await build_menu_context(
        target=callback,
        state=state,
        profile=profile,
        admin_ids=admin_ids,
        moderator_ids=moderator_ids,
        bot_switch=bot_switch,
    )
    await render_menu(context)


def _order_stats(stats: RatingStats) -> tuple[int, int, int, int]:
    complete = stats.complete
    incomplete = stats.incomplete + stats.not_taken
    total = complete + incomplete
    rate_full = round(complete / total * 100) if total else 0
    return complete, incomplete, total, rate_full


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
    complete, incomplete, total, rate_full = _order_stats(stats)
    prices = (
        format_prices_table(profile.prices) if profile is not None else "<code>-</code>"
    )
    speed = stats.speed_seconds if stats.speed_seconds is not None else "-"
    text = _("start.priority").format(
        speed=speed,
        prices=prices,
        total=total,
        complete=complete,
        incomplete=incomplete,
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
    admin_ids: frozenset[int],
    moderator_ids: frozenset[int],
    bot_switch: BotSwitchService,
) -> None:
    context = await build_menu_context(
        target=callback,
        state=state,
        profile=profile,
        admin_ids=admin_ids,
        moderator_ids=moderator_ids,
        bot_switch=bot_switch,
    )
    await open_menu(context)
    await callback.answer()
