import html
import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import BaseFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import BaseStorage, StorageKey
from aiogram.types import CallbackQuery, User
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n import gettext as _

from bot.forms import fields
from bot.forms.menu import send_menu
from bot.forms.states import Moderation
from bot.keyboards.profile import PackagesDoneCB
from bot.utils.telegram import ignore_not_modified
from common.catalog.tiers import Tier, tier_for_packages
from common.keyboards.moderation import (
    ModApproveCB,
    ModDenyCB,
    ModEditPacksCB,
    ModSetTierCB,
    ModToggleCodesCB,
    moderation_decision_kb,
)
from common.models.user_profiles import UserProfile
from common.repositories.user_profiles import UserProfileRepository
from common.services.moderation import is_moderator, render_pending_review

logger = logging.getLogger(__name__)

router = Router(name="moderation")

_MOD_PROFILE_ID_KEY = "mod_profile_id"
_MOD_WITH_CODES_KEY = "mod_with_codes"
_LOCALE_KEY = "locale"


class _IsModerator(BaseFilter):
    async def __call__(
        self,
        callback: CallbackQuery,
        moderator_ids: frozenset[int],
        profiles: UserProfileRepository,
    ) -> bool:
        user = callback.from_user
        if user is None:
            return False
        return await is_moderator(
            profiles=profiles,
            moderator_ids=moderator_ids,
            tg_id=user.id,
        )


_is_moderator = _IsModerator()


def _moderator_label(user: User) -> str:
    return f"@{user.username}" if user.username else f"id={user.id}"


async def _annotate(*, callback: CallbackQuery, note: str) -> None:
    base = callback.message.text or ""
    text = f"{base}\n\n{note}" if base else note
    await callback.message.edit_text(html.escape(text), reply_markup=None)


# This runs inside the moderator's callback, so the active i18n contextvar holds the
# moderator's locale. The recipient's locale is passed in explicitly and applied via
# use_locale so the user is notified in their own language, not the moderator's.
async def _notify_approved(
    *,
    bot: Bot,
    profile: UserProfile,
    state: FSMContext,
    i18n: I18n,
    locale: str,
) -> None:
    try:
        with i18n.use_locale(locale):
            await bot.send_message(chat_id=profile.tg_id, text=_("start.approved"))
            await send_menu(
                bot=bot,
                chat_id=profile.tg_id,
                state=state,
                profile=profile,
            )
    except TelegramAPIError:
        logger.exception(
            "failed to notify approved user profile_id=%s tg_id=%s",
            profile.id,
            profile.tg_id,
        )


def _user_state(*, storage: BaseStorage, bot: Bot, tg_id: int) -> FSMContext:
    key = StorageKey(bot_id=bot.id, chat_id=tg_id, user_id=tg_id)
    return FSMContext(storage=storage, key=key)


@router.callback_query(ModToggleCodesCB.filter(), _is_moderator)
async def toggle_with_codes(
    callback: CallbackQuery,
    callback_data: ModToggleCodesCB,
) -> None:
    await callback.message.edit_reply_markup(
        reply_markup=moderation_decision_kb(
            profile_id=callback_data.profile_id,
            with_codes=not callback_data.with_codes,
            tier=callback_data.tier,
        ),
    )
    await callback.answer()


@router.callback_query(ModSetTierCB.filter(), _is_moderator)
async def set_tier(
    callback: CallbackQuery,
    callback_data: ModSetTierCB,
) -> None:
    # Re-tapping the already-selected tier yields identical markup, which Telegram
    # rejects with "message is not modified"; ignore that no-op only.
    with ignore_not_modified():
        await callback.message.edit_reply_markup(
            reply_markup=moderation_decision_kb(
                profile_id=callback_data.profile_id,
                with_codes=callback_data.with_codes,
                tier=callback_data.tier,
            ),
        )
    await callback.answer()


@router.callback_query(ModEditPacksCB.filter(), _is_moderator)
async def open_pack_editor(
    callback: CallbackQuery,
    callback_data: ModEditPacksCB,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    profile = await profiles.get_by_id(profile_id=callback_data.profile_id)
    if profile is None:
        await callback.answer(_("moderation.profile_not_found"), show_alert=True)
        return
    await state.set_state(Moderation.packages)
    await state.update_data(
        {
            _MOD_PROFILE_ID_KEY: callback_data.profile_id,
            _MOD_WITH_CODES_KEY: callback_data.with_codes,
            "tier": callback_data.tier,
            "prices": {str(size): price for size, price in (profile.prices or {}).items()},
        },
    )
    await fields.show_packages_grid(target=callback, state=state)
    await callback.answer()


@router.callback_query(Moderation.packages, PackagesDoneCB.filter(), _is_moderator)
async def save_packs(
    callback: CallbackQuery,
    state: FSMContext,
    profiles: UserProfileRepository,
) -> None:
    if not await fields.ensure_packages_selected(callback=callback, state=state):
        return
    data = await state.get_data()
    profile_id = data[_MOD_PROFILE_ID_KEY]
    with_codes = data[_MOD_WITH_CODES_KEY]
    prices = {int(size): int(price) for size, price in data["prices"].items()}
    try:
        profile = await profiles.set_prices(profile_id=profile_id, prices=prices)
    except LookupError:
        await callback.answer(_("moderation.profile_not_found"), show_alert=True)
        return
    tier = max(Tier(data["tier"]), tier_for_packages(prices))
    await state.set_state(None)
    await callback.message.edit_text(
        render_pending_review(profile=profile, tier=tier),
        reply_markup=moderation_decision_kb(
            profile_id=profile_id,
            with_codes=with_codes,
            tier=int(tier),
        ),
    )
    await callback.answer(_("moderation.packages_saved"))


@router.callback_query(ModApproveCB.filter(), _is_moderator)
async def approve_user(
    callback: CallbackQuery,
    callback_data: ModApproveCB,
    bot: Bot,
    profiles: UserProfileRepository,
    fsm_storage: BaseStorage,
    i18n: I18n,
) -> None:
    try:
        profile = await profiles.approve(
            profile_id=callback_data.profile_id,
            with_codes=callback_data.with_codes,
            tier=Tier(callback_data.tier),
        )
    except LookupError:
        await callback.answer(_("moderation.profile_not_found"), show_alert=True)
        return
    user_state = _user_state(storage=fsm_storage, bot=bot, tg_id=profile.tg_id)
    user_locale = (await user_state.get_data()).get(_LOCALE_KEY) or i18n.default_locale
    await user_state.clear()
    await _annotate(
        callback=callback,
        note=f"#approved by {_moderator_label(callback.from_user)}",
    )
    await callback.answer()
    await _notify_approved(
        bot=bot,
        profile=profile,
        state=user_state,
        i18n=i18n,
        locale=user_locale,
    )


@router.callback_query(ModDenyCB.filter(), _is_moderator)
async def deny_user(callback: CallbackQuery) -> None:
    await _annotate(
        callback=callback,
        note=f"#denied by {_moderator_label(callback.from_user)}",
    )
    await callback.answer()
