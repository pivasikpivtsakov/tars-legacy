import logging
from typing import Any

from aiogram import Bot
from asyncpg import Pool

from api.schemas.order import (
    OrderCreate,
    OrderResponse,
)
from common.exceptions import (
    ControllerAuthorizationError,
    OrderProcessingError,
    ResourceAlreadyExistsError,
)
from common.models.orders import ExternalOrderStatus
from common.models.orders import Order as OrderEntity
from common.repositories.order_offers import OrderOfferRepository
from common.repositories.orders import OrderRepository
from common.repositories.pending_orders import PendingOrdersRepository
from common.repositories.user_roles import UserRole, UserRoleRepository
from common.schemas.external_order import ExternalOrder
from common.services.broadcast import BroadcastService
from common.services.external_order_api import ExternalOrderApi
from common.services.order_processing import forward_to_third_party

logger = logging.getLogger(__name__)


class OrderEntityService:
    def __init__(
        self,
        pool: Pool,
        bot: Bot,
        broadcast: BroadcastService,
        orders: OrderRepository,
        offers: OrderOfferRepository,
        pending: PendingOrdersRepository,
        external_api: ExternalOrderApi,
        roles: UserRoleRepository,
    ) -> None:
        self.pool = pool
        self.bot = bot
        self.broadcast = broadcast
        self.order_repo = orders
        self.offer_repo = offers
        self.pending_repo = pending
        self.external_api = external_api
        self.roles = roles

    async def create(self, data: OrderCreate) -> OrderResponse | None:
        if await self.order_repo.get_by_original_id(original_id=data.id):
            msg = "Order with id already exists"
            raise ResourceAlreadyExistsError(msg)

        moderator_ids = await self.roles.get(role=UserRole.MODERATOR)
        order = ExternalOrder(original_id=data.id, **data.model_dump(exclude={"id"}))
        try:
            order = await self.external_api.get_order(order=order)

            if order.amount is None:
                msg = f"Order amount is not found for {order.original_id=}"
                await self.broadcast.send_to_user_ids(
                    bot=self.bot, user_ids=moderator_ids, text=msg
                )
                await forward_to_third_party(original_id=order.original_id)
                return None

            await self.external_api.change_order_status(order)
            if order.unused_codes:
                order, msg_to_admin = await self.external_api.check_unused_codes(order)
                for msg in msg_to_admin:
                    await self.broadcast.send_to_user_ids(
                        bot=self.bot, user_ids=moderator_ids, text=msg
                    )
            if not order.unused_codes:
                msg = (
                    "✖️ <b>Передан заказ без неиспользованных"
                    f" кодов: {order.original_id}</b>\n"
                    "Прекращаем обработку"
                )
                await self.broadcast.send_to_user_ids(
                    bot=self.bot, user_ids=moderator_ids, text=msg
                )
                order.status = ExternalOrderStatus.REDEEMED
                order.status_reason = None
                await self._insert(order)
                await self.external_api.send_update_codes(order)
                await self.external_api.send_complete_order(order, is_w_codes=False)
                return None
        except (OrderProcessingError, ControllerAuthorizationError) as ex:
            await self.broadcast.send_to_user_ids(
                bot=self.bot, user_ids=moderator_ids, text=ex.message
            )
            raise
        entity = await self._insert(order)
        return OrderResponse.model_validate(entity)

    async def get(
        self,
        order_id: int | None = None,
        original_id: int | None = None,
    ) -> OrderEntity | None:
        if order_id:
            return await self.order_repo.get(order_id=order_id)
        if original_id:
            return await self.order_repo.get_by_original_id(original_id=original_id)
        return None

    async def clean_order(self, order_id: int, original_id: int) -> None:
        order = None
        if order_id:
            order = await self.order_repo.get(order_id=order_id)
        if original_id:
            order = await self.order_repo.get_by_original_id(original_id=original_id)
        if order is None:
            return
        # cancel order, expire offers, release counters
        async with self.pool.acquire() as conn, conn.transaction():
            await self.order_repo.mark_cancelled(order_id=order.id, conn=conn)
            released_user_ids = await self.offer_repo.expire_offered(order_id=order.id, conn=conn)
        await self.pending_repo.release_many(user_ids=released_user_ids)

    async def _insert(self, order: ExternalOrder) -> OrderEntity:
        return await self.order_repo.add(
            original_id=order.original_id,
            **self._order_columns(order),
        )

    @staticmethod
    def _order_columns(order: ExternalOrder) -> dict[str, Any]:
        return {
            "shop_access_key": order.shop_access_key,
            "amount": order.amount,
            "pubg_id": order.pubg_id,
            "codes": order.codes,
            "unused_codes": order.unused_codes,
            "broken_codes": tuple(order.broken_codes),
            "redeemed_codes": tuple(order.redeemed_codes),
            "additional_data": order.additional_data,
            "external_status": order.status,
            "status_reason": order.status_reason,
            "is_only_w_codes": order.is_only_w_codes,
        }
