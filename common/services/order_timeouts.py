import contextlib
import logging
from collections.abc import Sequence
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from common.i18n import gettext_for
from common.keyboards.orders import checkin_inline_kb, last_call_inline_kb
from common.models.orders import OrderStatus
from common.rendering.orders import render_checkin_text, render_last_call_text
from common.repositories.postgres.orders import OrderRepository
from common.repositories.redis.language import LanguageRepository
from common.repositories.redis.order_timeout_messages import OrderTimeoutMessageStore
from common.services.order_processing import OrderLifecycle

logger = logging.getLogger(__name__)

_MESSAGE_TTL_BUFFER_SECONDS = 300


class OrderTimeoutService:
    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler,
        bot: Bot,
        redis: Redis,
        orders: OrderRepository,
        lifecycle: OrderLifecycle,
        language: LanguageRepository,
        notification_1_delay: int,
        notification_2_delay: int,
        expiry_delay: int,
    ) -> None:
        self._scheduler = scheduler
        self._bot = bot
        self._orders = orders
        self._lifecycle = lifecycle
        self._language = language
        self._notification_1_delay = notification_1_delay
        self._notification_2_delay = notification_2_delay
        self._expiry_delay = expiry_delay
        self._messages = OrderTimeoutMessageStore(redis=redis)
        self._message_ttl = (
            notification_1_delay
            + notification_2_delay
            + expiry_delay
            + _MESSAGE_TTL_BUFFER_SECONDS
        )

    def _job_id(self, order_id: int) -> str:
        return f"order_timeout:{order_id}"

    def _schedule(self, *, func_ref: str, order_id: int, delay: int, **kwargs: int) -> None:
        run_date = datetime.now(tz=self._scheduler.timezone) + timedelta(seconds=delay)
        self._scheduler.add_job(
            func_ref,
            trigger="date",
            run_date=run_date,
            id=self._job_id(order_id),
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=None,
            kwargs={"order_id": order_id, **kwargs},
        )

    async def start(
        self,
        *,
        order_id: int,
        user_id: int,
        chat_id: int,
        message_id: int,
        timed_out_text: str,
    ) -> None:
        self._schedule(
            func_ref="common.jobs.order_timeouts:order_expiry_notification_1",
            order_id=order_id,
            delay=self._notification_1_delay,
            user_id=user_id,
            chat_id=chat_id,
        )
        await self._messages.remember_taken(
            order_id=order_id,
            chat_id=chat_id,
            message_id=message_id,
            timed_out_text=timed_out_text,
            ttl_seconds=self._message_ttl,
        )

    async def clear(self, *, order_id: int) -> None:
        with contextlib.suppress(JobLookupError):
            self._scheduler.remove_job(self._job_id(order_id))
        messages = await self._messages.pop(order_id=order_id)
        if messages is not None:
            await self._delete_pings(
                chat_id=messages.chat_id,
                message_ids=messages.ping_message_ids,
            )

    async def _in_work(self, *, order_id: int, user_id: int) -> bool:
        order = await self._orders.get(order_id=order_id)
        if order is None:
            return False
        return order.status is OrderStatus.TAKEN and order.taken_by == user_id

    async def run_order_expiry_notification_1(
        self, *, order_id: int, user_id: int, chat_id: int
    ) -> None:
        if not await self._in_work(order_id=order_id, user_id=user_id):
            return
        translate = gettext_for(await self._language.get(tg_id=chat_id))
        await self._notify(
            order_id=order_id,
            chat_id=chat_id,
            text=render_checkin_text(
                minutes=(self._notification_2_delay + self._expiry_delay) // 60,
                gettext=translate,
            ),
            reply_markup=checkin_inline_kb(
                order_id=order_id,
                yes_text=translate("order.btn_checkin_yes"),
                spacer_text=translate("order.btn_noop"),
                no_text=translate("order.btn_checkin_no"),
            ),
        )
        self._schedule(
            func_ref="common.jobs.order_timeouts:order_expiry_notification_2",
            order_id=order_id,
            delay=self._notification_2_delay,
            user_id=user_id,
            chat_id=chat_id,
        )

    async def run_order_expiry_notification_2(
        self, *, order_id: int, user_id: int, chat_id: int
    ) -> None:
        if not await self._in_work(order_id=order_id, user_id=user_id):
            return
        locale = await self._language.get(tg_id=chat_id)
        translate = gettext_for(locale)
        await self._notify(
            order_id=order_id,
            chat_id=chat_id,
            text=render_last_call_text(
                minutes=self._expiry_delay // 60,
                gettext=translate,
            ),
            reply_markup=last_call_inline_kb(
                order_id=order_id,
                working_text=translate("order.btn_working"),
                spacer_text=translate("order.btn_noop"),
                cancel_text=translate("order.btn_cancel"),
            ),
        )
        self._schedule(
            func_ref="common.jobs.order_timeouts:order_expiry",
            order_id=order_id,
            delay=self._expiry_delay,
            user_id=user_id,
        )

    async def run_order_expiry(self, *, order_id: int, user_id: int) -> None:
        if not await self._in_work(order_id=order_id, user_id=user_id):
            return
        await self._lifecycle.expire_taken(order_id=order_id, user_id=user_id)
        await self._render_timed_out(order_id=order_id)

    async def _render_timed_out(self, *, order_id: int) -> None:
        messages = await self._messages.pop(order_id=order_id)
        if messages is None:
            return
        with contextlib.suppress(TelegramAPIError):
            await self._bot.edit_message_text(
                text=messages.timed_out_text,
                chat_id=messages.chat_id,
                message_id=messages.taken_message_id,
                reply_markup=None,
            )
        await self._delete_pings(
            chat_id=messages.chat_id,
            message_ids=messages.ping_message_ids,
        )

    async def _delete_pings(self, *, chat_id: int, message_ids: Sequence[int]) -> None:
        for message_id in message_ids:
            with contextlib.suppress(TelegramAPIError):
                await self._bot.delete_message(chat_id=chat_id, message_id=message_id)

    async def _notify(
        self,
        *,
        order_id: int,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup,
    ) -> None:
        try:
            sent = await self._bot.send_message(
                chat_id=chat_id, text=text, reply_markup=reply_markup
            )
        except TelegramAPIError:
            logger.exception("failed to send order timeout prompt chat_id=%s", chat_id)
            return
        await self._messages.add_ping(order_id=order_id, message_id=sent.message_id)
