import asyncio
import html
import random
import sys

from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.i18n import I18n

from common.i18n import DOMAIN, LOCALES_DIR
from common.repositories.bot_switch import BotSwitchRepository
from common.repositories.online_price_index import OnlinePriceIndex
from common.repositories.orders import OrderRepository
from common.repositories.user_profiles import UserProfileRepository

router = Router(name="admin")


class _IsAdmin(BaseFilter):
    async def __call__(
        self,
        message: Message,
        admin_ids: frozenset[int],
    ) -> bool:
        user = message.from_user
        return user is not None and user.id in admin_ids


_is_admin = _IsAdmin()


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


@router.message(Command("approve", prefix="#"), _is_admin)
async def cmd_approve(
    message: Message,
    command: CommandObject,
    profiles: UserProfileRepository,
) -> None:
    args = (command.args or "").split()
    if not args:
        await message.answer("usage: #approve <tg_id> [codes]")
        return
    try:
        tg_id = int(args[0])
    except ValueError:
        await message.answer("tg_id must be an integer")
        return
    with_codes = len(args) > 1 and args[1].casefold() in {"codes", "1", "true", "yes"}
    profile = await profiles.get_by_tg_id(tg_id=tg_id)
    if profile is None:
        await message.answer(f"no profile for tg_id={tg_id}")
        return
    updated = await profiles.approve(profile_id=profile.id, with_codes=with_codes)
    await message.answer(
        f"approved tg_id={tg_id}: status={updated.status.value}, "
        f"with_codes={updated.with_codes}",
    )


@router.message(Command("enable", prefix="#"), _is_admin)
async def cmd_enable(message: Message, bot_switch: BotSwitchRepository) -> None:
    await bot_switch.enable()
    await message.answer("bot enabled")


@router.message(Command("disable", prefix="#"), _is_admin)
async def cmd_disable(message: Message, bot_switch: BotSwitchRepository) -> None:
    await bot_switch.disable()
    await message.answer("bot disabled")


@router.message(Command("create_order", prefix="#"), _is_admin)
async def cmd_create_order(message: Message, orders: OrderRepository) -> None:
    # currently fakes! no order source yet
    order = await orders.create(
        original_id=random.randint(1, 1_000_000),
        amount=385,
        pubg_id=random.randint(10_000_000, 9_999_999_999),
    )
    await message.answer(
        f"order id={order.id} created (status={order.status.value}); "
        f"fanout job will dispatch it",
    )
