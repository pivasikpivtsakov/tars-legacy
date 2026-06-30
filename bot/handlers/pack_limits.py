from collections.abc import Mapping
from decimal import Decimal

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from bot.forms.states import PackPriceLimits
from bot.keyboards.pack_limits import (
    PackLimitCancelCB,
    PackLimitEditCB,
    PackLimitResetCB,
    pack_limit_prompt_kb,
    pack_limits_kb,
)
from bot.keyboards.start import OpenZoneCB, StartZone
from common.catalog.packages import format_prices_table
from common.money import format_money, parse_money
from common.repositories.redis.pack_price_limits import PackPriceLimitRepository
from common.services.moderation import ModerationService

router = Router(name="pack_limits")

_LIMIT_SIZE_KEY = "pack_limit_size"
_LIMIT_MSG_KEY = "pack_limit_msg_id"
_MAX_PACK_LIMIT = Decimal(1_000_000)


class _IsStaff(BaseFilter):
    async def __call__(
        self,
        event: Message | CallbackQuery,
        admin_ids: frozenset[int],
        moderator_ids: frozenset[int],
        moderation: ModerationService,
    ) -> bool:
        user = event.from_user
        if user is None:
            return False
        return await moderation.is_staff(
            admin_ids=admin_ids,
            moderator_ids=moderator_ids,
            tg_id=user.id,
        )


_is_staff = _IsStaff()


def _parse_limit(raw: str) -> Decimal | None:
    value = parse_money(raw)
    if value is None or value <= 0 or value > _MAX_PACK_LIMIT:
        return None
    return value


def _panel_view(limits: Mapping[int, Decimal]) -> tuple[str, InlineKeyboardMarkup]:
    return (
        _("admin.pack_limits_title").format(limits=format_prices_table(limits)),
        pack_limits_kb(
            reset_text=_("admin.btn_pack_limits_reset"),
            back_text=_("start.btn_back"),
        ),
    )


async def _render_panel(
    *,
    callback: CallbackQuery,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    await state.set_state(None)
    text, markup = _panel_view(await pack_price_limits.get_all())
    await callback.message.edit_text(text, reply_markup=markup)


@router.callback_query(OpenZoneCB.filter(F.value == StartZone.PACK_PRICE_LIMITS), _is_staff)
async def open_pack_limits(
    callback: CallbackQuery,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    await _render_panel(callback=callback, state=state, pack_price_limits=pack_price_limits)
    await callback.answer()


@router.callback_query(PackLimitEditCB.filter(), _is_staff)
async def prompt_pack_limit(
    callback: CallbackQuery,
    callback_data: PackLimitEditCB,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    current = await pack_price_limits.get(size=callback_data.size)
    await state.set_state(PackPriceLimits.awaiting_value)
    await state.update_data(
        {_LIMIT_SIZE_KEY: callback_data.size, _LIMIT_MSG_KEY: callback.message.message_id},
    )
    await callback.message.edit_text(
        _("admin.pack_limits_prompt").format(
            size=callback_data.size,
            current=format_money(current),
        ),
        reply_markup=pack_limit_prompt_kb(cancel_text=_("registration.btn_cancel_pack")),
    )
    await callback.answer()


@router.callback_query(PackLimitResetCB.filter(), _is_staff)
async def reset_pack_limits(
    callback: CallbackQuery,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    await pack_price_limits.reset_all()
    await _render_panel(callback=callback, state=state, pack_price_limits=pack_price_limits)
    await callback.answer(_("admin.pack_limits_reset_done"))


@router.callback_query(PackLimitCancelCB.filter(), _is_staff)
async def cancel_pack_limit(
    callback: CallbackQuery,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    await _render_panel(callback=callback, state=state, pack_price_limits=pack_price_limits)
    await callback.answer()


@router.message(PackPriceLimits.awaiting_value, F.text)
async def apply_pack_limit(
    message: Message,
    state: FSMContext,
    pack_price_limits: PackPriceLimitRepository,
) -> None:
    value = _parse_limit(message.text)
    if value is None:
        await message.answer(
            _("admin.pack_limits_invalid").format(max=format_money(_MAX_PACK_LIMIT)),
        )
        return
    data = await state.get_data()
    # Caps are non-retroactive: they're only enforced at price-input time
    # (parse_price). Lowering a cap does not re-validate or recompute prices
    # already stored on user profiles; over-cap users keep their price until
    # they next edit that pack.
    await pack_price_limits.set(size=data[_LIMIT_SIZE_KEY], limit=value)
    await state.set_state(None)
    text, markup = _panel_view(await pack_price_limits.get_all())
    message_id = data.get(_LIMIT_MSG_KEY)
    if message_id is not None:
        try:
            await message.bot.edit_message_text(
                text=text,
                chat_id=message.chat.id,
                message_id=message_id,
                reply_markup=markup,
            )
            return
        except TelegramBadRequest:
            pass
    await message.answer(text, reply_markup=markup)
