from dataclasses import dataclass
from enum import StrEnum

from common.models.orders import Order, OrderStatus
from common.models.user_profiles import UserProfile
from common.repositories.postgres.orders import OrderRepository
from common.schemas.external_order import ExternalOrder
from common.services.external_order_api import ExternalOrderApi
from common.services.user_profiles import UserProfileService


class FraudVerdict(StrEnum):
    OK = "ok"
    UNFINISHED = "unfinished"
    FRAUD = "fraud"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class FraudReview:
    verdict: FraudVerdict
    order: Order | None = None
    unverified_codes: tuple[str, ...] = ()


def _to_external(order: Order) -> ExternalOrder:
    return ExternalOrder(
        id=order.id,
        original_id=order.original_id,
        shop_access_key=order.shop_access_key,
        amount=order.amount,
        pubg_id=order.pubg_id,
        unused_codes=order.unused_codes or {},
        additional_data=order.additional_data or {},
    )


class AntiFraudService:
    def __init__(
        self,
        *,
        orders: OrderRepository,
        external_api: ExternalOrderApi,
        user_profiles: UserProfileService,
    ) -> None:
        self._orders = orders
        self._external_api = external_api
        self._user_profiles = user_profiles

    async def review(
        self,
        *,
        order_id: int,
        profile: UserProfile,
        block_on_fraud: bool,
    ) -> FraudReview:
        order = await self._orders.get(order_id=order_id)
        if order is None or order.taken_by != profile.id or order.status is not OrderStatus.TAKEN:
            return FraudReview(verdict=FraudVerdict.UNAVAILABLE)
        ok, is_fraud, unverified_codes = await self._external_api.check_order_finished(
            order=_to_external(order),
            user_id=profile.id,
            is_w_codes=profile.with_codes,
        )
        unverified = tuple(unverified_codes)
        if is_fraud:
            if block_on_fraud:
                await self._user_profiles.block(profile_id=profile.id)
            return FraudReview(
                verdict=FraudVerdict.FRAUD, order=order, unverified_codes=unverified
            )
        if not ok:
            return FraudReview(
                verdict=FraudVerdict.UNFINISHED, order=order, unverified_codes=unverified
            )
        return FraudReview(verdict=FraudVerdict.OK, order=order, unverified_codes=unverified)
