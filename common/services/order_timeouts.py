import contextlib
import logging
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from common.i18n import build_i18n
from common.keyboards.orders import checkin_inline_kb, last_call_inline_kb
from common.models.orders import OrderStatus
from common.rendering.orders import render_checkin_text, render_last_call_text
from common.repositories.orders import OrderRepository
from common.services.order_processing import OrderLifecycle

logger = logging.getLogger(__name__)


class OrderTimeoutService:
    def __init__(
        self,
        *,
        scheduler: AsyncIOScheduler,
        bot: Bot,
        orders: OrderRepository,
        lifecycle: OrderLifecycle,
        notification_1_delay: int,
        notification_2_delay: int,
        expiry_delay: int,
    ) -> None:
        self._scheduler = scheduler
        self._bot = bot
        self._orders = orders
        self._lifecycle = lifecycle
        self._notification_1_delay = notification_1_delay
        self._notification_2_delay = notification_2_delay
        self._expiry_delay = expiry_delay
        self._gettext = build_i18n().gettext

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

    def start(self, *, order_id: int, user_id: int, chat_id: int) -> None:
        self._schedule(
            func_ref="common.jobs.order_timeouts:order_expiry_notification_1",
            order_id=order_id,
            delay=self._notification_1_delay,
            user_id=user_id,
            chat_id=chat_id,
        )

    def clear(self, *, order_id: int) -> None:
        with contextlib.suppress(JobLookupError):
            self._scheduler.remove_job(self._job_id(order_id))

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
        await self._notify(
            chat_id=chat_id,
            text=render_checkin_text(
                minutes=(self._notification_2_delay + self._expiry_delay) // 60,
                gettext=self._gettext,
            ),
            reply_markup=checkin_inline_kb(
                order_id=order_id,
                yes_text=self._gettext("order.btn_checkin_yes"),
                spacer_text=self._gettext("order.btn_noop"),
                no_text=self._gettext("order.btn_checkin_no"),
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
        await self._notify(
            chat_id=chat_id,
            text=render_last_call_text(
                minutes=self._expiry_delay // 60,
                gettext=self._gettext,
            ),
            reply_markup=last_call_inline_kb(
                order_id=order_id,
                working_text=self._gettext("order.btn_working"),
                spacer_text=self._gettext("order.btn_noop"),
                cancel_text=self._gettext("order.btn_cancel"),
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

    async def _notify(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: InlineKeyboardMarkup,
    ) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        except TelegramAPIError:
            logger.exception("failed to send order timeout prompt chat_id=%s", chat_id)
