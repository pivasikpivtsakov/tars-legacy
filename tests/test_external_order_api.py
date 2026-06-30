import asyncio

import pytest

from common.exceptions.orders import OrderProcessingError
from common.models.orders import ExternalOrderStatus
from common.schemas.external_order import ExternalOrder
from common.services.external_order_api import (
    PATH_CODE_EXCHANGE_TIME,
    PATH_ORDER_GET,
    ExternalOrderApi,
)
from common.services.external_order_mock import (
    MOCK_DEFAULT_CODE,
    MOCK_ORDER_AMOUNT,
    MOCK_PLAYER_OPEN_ID,
    MockRequestService,
    code_exchange_time_response,
    default_external_responses,
)
from common.services.request_service import MethodsEnum


def _api(responses: dict[tuple[str, MethodsEnum], tuple[int, object]]) -> ExternalOrderApi:
    return ExternalOrderApi(
        requests=MockRequestService(responses=responses),
    )


def test_get_order_populates_order_from_pending_response() -> None:
    api = _api(default_external_responses())

    order = asyncio.run(api.get_order(order=ExternalOrder(original_id=1)))

    assert order is not None
    assert order.amount == MOCK_ORDER_AMOUNT
    assert order.shop_access_key == "mock-shop-access-key"
    assert order.status == ExternalOrderStatus.PENDING


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


def test_check_unused_codes_keeps_valid_available_code_without_admin_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("common.services.external_order_api.APP_ENVIRONMENT", "production")
    api = _api(default_external_responses())

    order, messages = asyncio.run(
        api.check_unused_codes(
            order=ExternalOrder(
                original_id=4,
                shop_access_key="mock-shop-access-key",
                unused_codes={MOCK_DEFAULT_CODE: 60},
                additional_data={"player_open_id": MOCK_PLAYER_OPEN_ID},
            )
        )
    )

    assert messages == []
    assert order.unused_codes == {MOCK_DEFAULT_CODE: 60}
    assert order.redeemed_codes == []


def test_check_unused_codes_reports_previously_redeemed_code_for_same_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("common.services.external_order_api.APP_ENVIRONMENT", "production")
    responses = default_external_responses(
        overrides={
            (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(
                is_redeemed=True
            ),
        }
    )
    api = _api(responses)

    order, messages = asyncio.run(
        api.check_unused_codes(
            order=ExternalOrder(
                original_id=5,
                shop_access_key="mock-shop-access-key",
                unused_codes={MOCK_DEFAULT_CODE: 60},
                additional_data={"player_open_id": MOCK_PLAYER_OPEN_ID},
            )
        )
    )

    assert order.unused_codes == {}
    assert order.redeemed_codes == [MOCK_DEFAULT_CODE]
    assert messages == [
        f"🙆‍♂️ <b>Найден корректно активированный ранее код: {MOCK_DEFAULT_CODE}"
        f" в заказе: {order.original_id}</b>"
    ]
