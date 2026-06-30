from decimal import Decimal

from aiogram import F, Router
from aiogram.filters import BaseFilter, CommandStart
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
    send_online_state,
    show_back_panel,
    show_panel,
)
from bot.keyboards.menu import (
    ONLINE_STATE_OFF_KEY,
    ONLINE_STATE_ON_KEY,
    reply_text_matches,
)
from bot.keyboards.start import (
    BackCB,
    HistoryPageCB,
    OpenZoneCB,
    StartZone,
    balance_kb,
    history_kb,
)
from bot.middlewares.profile import require_active_profile
from common.catalog.packages import format_prices_table
from common.models.rating import RatingStats
from common.models.user_profiles import UserProfile
from common.money import format_money
from common.rendering.orders import render_transaction_history
from common.repositories.postgres.transactions import TransactionsRepository
from common.repositories.postgres.user_profiles import UserProfileRepository
from common.repositories.redis.online_index import OnlineIndexRouter
from common.repositories.redis.rating import RatingRepository
from common.services.bot_switch import BotSwitchService

_HISTORY_PAGE_SIZE = 10

router = Router(name="start")


class _IsOnlineToggle(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        text = message.text
        if text is None:
            return False
        return reply_text_matches(text, ONLINE_STATE_ON_KEY, ONLINE_STATE_OFF_KEY)


_is_online_toggle = _IsOnlineToggle()


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
        await install_menu_button(
            message=message,
            profile=profile,
            is_moderator=profile.id in moderator_ids,
        )
    context = await build_menu_context(
        target=message,
        state=state,
        profile=profile,
        admin_ids=admin_ids,
        moderator_ids=moderator_ids,
        bot_switch=bot_switch,
    )
    await render_menu(context)


@router.message(_is_online_toggle)
@require_active_profile
async def toggle_online(
    message: Message,
    profiles: UserProfileRepository,
    online_price_index: OnlineIndexRouter,
    profile: UserProfile,
    moderator_ids: frozenset[int],
) -> None:
    if profile.id in moderator_ids:
        return
    profile = await profiles.toggle_is_online_and_get(profile_id=profile.id)
    await online_price_index.sync(profile=profile)
    await send_online_state(message=message, profile=profile)


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
    if profile is not None and profile.with_codes:
        online = _("registration.btn_yes") if profile.is_online else _("registration.btn_no")
        text = _("start.priority_codes").format(
            tier=profile.tier.name(),
            online=online,
        )
        await show_back_panel(callback=callback, text=text)
        return
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
    transactions: TransactionsRepository,
) -> None:
    balance = (
        await transactions.balance_of(profile_id=profile.id)
        if profile is not None
        else Decimal(0)
    )
    await show_panel(
        callback=callback,
        text=_("start.balance").format(balance=format_money(balance)),
        markup=balance_kb(
            withdraw_text=_("start.btn_withdraw"),
            history_text=_("start.btn_history"),
            back_text=_("start.btn_back"),
        ),
    )


async def _show_history(
    *,
    callback: CallbackQuery,
    profile: UserProfile | None,
    transactions: TransactionsRepository,
    offset: int,
) -> None:
    if profile is None:
        groups, has_next = [], False
    else:
        groups, has_next = await transactions.history(
            profile_id=profile.id,
            limit=_HISTORY_PAGE_SIZE,
            offset=offset,
        )
    await show_panel(
        callback=callback,
        text=render_transaction_history(groups, has_next=has_next, gettext=_),
        markup=history_kb(
            offset=offset,
            limit=_HISTORY_PAGE_SIZE,
            has_next=has_next,
            prev_text=_("start.btn_prev"),
            next_text=_("start.btn_next"),
            back_text=_("start.btn_back"),
        ),
    )


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.HISTORY))
async def open_history(
    callback: CallbackQuery,
    profile: UserProfile | None,
    transactions: TransactionsRepository,
) -> None:
    await _show_history(callback=callback, profile=profile, transactions=transactions, offset=0)


@router.callback_query(HistoryPageCB.filter())
async def page_history(
    callback: CallbackQuery,
    callback_data: HistoryPageCB,
    profile: UserProfile | None,
    transactions: TransactionsRepository,
) -> None:
    await _show_history(
        callback=callback,
        profile=profile,
        transactions=transactions,
        offset=max(callback_data.offset, 0),
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
