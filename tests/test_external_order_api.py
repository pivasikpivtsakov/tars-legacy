import asyncio

import pytest

from api.testing import MockRequestService, default_external_responses
from common.exceptions.orders import OrderProcessingError
from common.models.orders import ExternalOrderStatus
from common.schemas.external_order import ExternalOrder
from common.services.external_order_api import PATH_ORDER_GET, ExternalOrderApi
from common.services.request_service import MethodsEnum

EXPECTED_AMOUNT = 60


class _FakeUserProfiles:
    def __init__(self) -> None:
        self.blocked: list[int] = []

    async def block(self, *, profile_id: int) -> None:
        self.blocked.append(profile_id)


def _api(responses: dict[tuple[str, MethodsEnum], tuple[int, object]]) -> ExternalOrderApi:
    return ExternalOrderApi(
        user_profiles=_FakeUserProfiles(),
        requests=MockRequestService(responses=responses),
    )


def test_get_order_populates_order_from_pending_response() -> None:
    api = _api(default_external_responses())

    order = asyncio.run(api.get_order(order=ExternalOrder(original_id=1)))

    assert order is not None
    assert order.amount == EXPECTED_AMOUNT
    assert order.shop_access_key == "mock-shop-access-key"
    assert order.status == ExternalOrderStatus.PENDING
    assert order.unused_codes == {"CODE-1": 60}


def test_get_order_rejects_unexpected_status() -> None:
    responses = default_external_responses()
    responses[(PATH_ORDER_GET, MethodsEnum.GET)] = (
        200,
        {"status": ExternalOrderStatus.REDEEMED, "amount": 60},
    )
    api = _api(responses)

    with pytest.raises(OrderProcessingError):
        asyncio.run(api.get_order(order=ExternalOrder(original_id=2)))


def test_get_order_raises_on_forbidden() -> None:
    responses = default_external_responses()
    responses[(PATH_ORDER_GET, MethodsEnum.GET)] = (403, {"detail": "forbidden"})
    api = _api(responses)

    with pytest.raises(OrderProcessingError):
        asyncio.run(api.get_order(order=ExternalOrder(original_id=3)))
