import asyncio
import html
import sys

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import I18n
from aiogram.utils.i18n import gettext as _

from bot.forms.menu import MenuContext, render_menu
from bot.keyboards.start import OpenZoneCB, StartZone
from common.i18n import DOMAIN, LOCALES_DIR
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.user_profiles import UserProfileRepository
from common.services.bot_switch import BotSwitchService
from common.services.broadcast import BroadcastService

router = Router(name="admin")


async def _is_admin_profile(
    *,
    tg_id: int,
    admin_ids: frozenset[int],
    profiles: UserProfileRepository,
) -> bool:
    if not admin_ids:
        return False
    profile = await profiles.get_by_tg_id(tg_id=tg_id)
    return profile is not None and profile.id in admin_ids


class _IsAdmin(BaseFilter):
    async def __call__(
        self,
        message: Message,
        admin_ids: frozenset[int],
        profiles: UserProfileRepository,
    ) -> bool:
        user = message.from_user
        if user is None:
            return False
        return await _is_admin_profile(
            tg_id=user.id,
            admin_ids=admin_ids,
            profiles=profiles,
        )


_is_admin = _IsAdmin()


class _IsAdminCallback(BaseFilter):
    async def __call__(
        self,
        callback: CallbackQuery,
        admin_ids: frozenset[int],
        profiles: UserProfileRepository,
    ) -> bool:
        return await _is_admin_profile(
            tg_id=callback.from_user.id,
            admin_ids=admin_ids,
            profiles=profiles,
        )


_is_admin_callback = _IsAdminCallback()


@router.message(Command("reload_locales", prefix="#"), _is_admin)
async def cmd_reload_locales(message: Message, i18n: I18n) -> None:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "babel.messages.frontend",
        "compile",
        "-d",
        str(LOCALES_DIR),
        "-D",
        DOMAIN,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    output, _stderr = await proc.communicate()
    if proc.returncode != 0:
        tail = html.escape(output.decode(errors="replace")[-3000:])
        await message.answer(
            f"compile failed (exit {proc.returncode}):\n<pre>{tail}</pre>",
        )
        return
    i18n.reload()
    locales = ", ".join(i18n.available_locales) or "<none>"
    await message.answer(f"reloaded locales: {locales}")


@router.message(Command("full_restart", prefix="#"), _is_admin)
async def cmd_full_restart(
    message: Message,
    state: FSMContext,
    profiles: UserProfileRepository,
    online_price_index: OnlinePriceIndex,
) -> None:
    profile = await profiles.get_by_tg_id(tg_id=message.from_user.id)
    if profile is not None:
        await online_price_index.remove(user_id=profile.id)
        await profiles.delete(profile_id=profile.id)
    await state.clear()
    await message.answer("profile and FSM state wiped")


@router.message(Command("enable", prefix="#"), _is_admin)
async def cmd_enable(
    message: Message,
    bot: Bot,
    bot_switch: BotSwitchService,
    broadcast: BroadcastService,
) -> None:
    await bot_switch.enable()
    await broadcast.send_to_everyone(bot=bot, text=_("admin.bot_online_announcement"))
    await message.answer(_("admin.bot_enabled"))


@router.message(Command("disable", prefix="#"), _is_admin)
async def cmd_disable(
    message: Message,
    bot: Bot,
    bot_switch: BotSwitchService,
    broadcast: BroadcastService,
) -> None:
    await bot_switch.disable()
    await broadcast.send_to_everyone(bot=bot, text=_("admin.bot_disabled_announcement"))
    await message.answer(_("admin.bot_disabled"))


@router.callback_query(
    OpenZoneCB.filter(F.value == StartZone.TOGGLE_BOT_ENABLED),
    _is_admin_callback,
)
async def toggle_bot_enabled(
    callback: CallbackQuery,
    bot: Bot,
    state: FSMContext,
    bot_switch: BotSwitchService,
    profiles: UserProfileRepository,
    broadcast: BroadcastService,
    moderator_ids: frozenset[int],
) -> None:
    enabled = await bot_switch.toggle()
    if enabled:
        await broadcast.send_to_everyone(bot=bot, text=_("admin.bot_online_announcement"))
    else:
        await broadcast.send_to_everyone(bot=bot, text=_("admin.bot_disabled_announcement"))
    profile = await profiles.get_by_tg_id(tg_id=callback.from_user.id)
    text = _("admin.bot_enabled") if enabled else _("admin.bot_disabled")
    await callback.answer(text, show_alert=False)
    await render_menu(
        MenuContext(
            target=callback,
            state=state,
            profile=profile,
            for_admin=True,
            bot_enabled=enabled,
            is_moderator=profile is not None and profile.id in moderator_ids,
        ),
    )
