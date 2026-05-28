import asyncio
import html
import random
import sys

from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.i18n import I18n

from bot.i18n import DOMAIN, LOCALES_DIR
from common.repositories.orders import OrderRepository
from common.repositories.user_profiles import UserProfileRepository
from common.services.order_processing import (
    OrderAmountError,
    OrderInput,
    OrderManager,
)

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
) -> None:
    await profiles.delete(user_id=message.from_user.id)
    await state.clear()
    await message.answer("profile and FSM state wiped")


@router.message(Command("create_order", prefix="#"), _is_admin)
async def cmd_create_order(message: Message, orders: OrderRepository, order_manager: OrderManager) -> None:
    # currently fakes! no order source yet
    order = await orders.create(
        original_id=random.randint(1, 1_000_000),
        # amount=random.randint(60, 2999),
        amount=385,
        pubg_id=random.randint(10_000_000, 9_999_999_999),
    )
    candidates = await order_manager.select_candidates(order=order)
    rendered = ", ".join(
        f"{c.user_id} (price={c.full_price})" for c in candidates
    )
    await message.answer(
        f"order id={order.id}\n"
        f"amount={order.amount}\n"
        f"ranked candidates: {rendered}",
    )
