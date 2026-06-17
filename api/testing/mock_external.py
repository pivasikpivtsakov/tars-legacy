from collections.abc import Mapping
from typing import Any

import httpx
from fastapi import FastAPI

from common.models.orders import ExternalOrderStatus
from common.services.external_order_api import (
    PATH_CODE_EXCHANGE_STATUS,
    PATH_CODE_EXCHANGE_TIME,
    PATH_CODES_GET,
    PATH_CODES_REPLACE,
    PATH_CODES_SET_STATUS,
    PATH_ORDER_COMPLETE,
    PATH_ORDER_GET,
    PATH_ORDER_UPDATE_CODES,
    PATH_ORDERS_SET_STATUS,
    PATH_SEND_MSG_TO_MODERATORS,
)
from common.services.request_service import MethodsEnum, RequestService

type ResponseKey = tuple[str, MethodsEnum]
type ResponseSpec = tuple[int, Any]

MOCK_ORDER_AMOUNT = 385
MOCK_PLAYER_OPEN_ID = "123456"
MOCK_FRAUD_OPEN_ID = "999999"


class MockRequestService(RequestService):
    def __init__(self, *, responses: Mapping[ResponseKey, ResponseSpec]) -> None:
        self._responses = dict(responses)
        self.calls: list[tuple[ResponseKey, dict[str, Any] | None, Any]] = []

    async def request(
        self,
        method: MethodsEnum,
        url: str,
        authorization_token: str,  # noqa: ARG002
        params: dict[str, Any] | None = None,
        data: Any = None,
        timeout: float = 25,  # noqa: ASYNC109, ARG002
    ) -> httpx.Response | None:
        path = httpx.URL(url).path
        key: ResponseKey = (path, method)
        self.calls.append((key, params, data))
        if key not in self._responses:
            msg = f"no mock response registered for {method.value} {path}"
            raise KeyError(msg)
        status_code, body = self._responses[key]
        return httpx.Response(
            status_code,
            json=body,
            request=httpx.Request(method.value, url),
        )


def code_exchange_time_response(
    *,
    is_redeemed: bool = True,
    exchange_open_id: str = MOCK_PLAYER_OPEN_ID,
    amount: int = 60,
) -> ResponseSpec:
    return (
        200,
        {
            "is_redeemed": is_redeemed,
            "exchange_open_id": exchange_open_id,
            "amount": amount,
        },
    )


def default_external_responses(
    *,
    overrides: Mapping[ResponseKey, ResponseSpec] | None = None,
) -> dict[ResponseKey, ResponseSpec]:
    responses: dict[ResponseKey, ResponseSpec] = {
        (PATH_ORDER_GET, MethodsEnum.GET): (
            200,
            {
                "status": ExternalOrderStatus.PENDING,
                "amount": MOCK_ORDER_AMOUNT,
                "shop_access_key": "mock-shop-access-key",
                "pubg_id": 123456,
                "status_reason": None,
                "codes": {"CODE-1": 60},
                "unused_codes": {"CODE-1": 60},
                "broken_codes": [],
                "redeemed_codes": [],
                "additional_data": {"player_open_id": MOCK_PLAYER_OPEN_ID},
            },
        ),
        (PATH_ORDERS_SET_STATUS, MethodsEnum.PATCH): (200, {"success": True}),
        (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(),
        (PATH_CODE_EXCHANGE_STATUS, MethodsEnum.GET): (200, {"is_redeemed": True}),
        (PATH_CODES_SET_STATUS, MethodsEnum.PATCH): (200, {"success": True}),
        (PATH_CODES_REPLACE, MethodsEnum.POST): (200, {"code": "CODE-REPLACED"}),
        (PATH_CODES_GET, MethodsEnum.GET): (200, [{"code": "CODE-NEW"}]),
        (PATH_ORDER_COMPLETE, MethodsEnum.PATCH): (200, {"success": True}),
        (PATH_ORDER_UPDATE_CODES, MethodsEnum.PUT): (200, {"success": True}),
        (PATH_SEND_MSG_TO_MODERATORS, MethodsEnum.POST): (200, {"success": True}),
    }
    if overrides:
        responses.update(overrides)
    return responses


def fraud_external_responses(
    *,
    exchange_open_id: str = MOCK_FRAUD_OPEN_ID,
) -> dict[ResponseKey, ResponseSpec]:
    """Code redeemed on a different open_id -> antifraud blocks the user."""
    return default_external_responses(
        overrides={
            (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(
                exchange_open_id=exchange_open_id
            ),
        }
    )


def unfinished_external_responses() -> dict[ResponseKey, ResponseSpec]:
    """Code not redeemed yet -> antifraud reports order as unfinished."""
    return default_external_responses(
        overrides={
            (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(
                is_redeemed=False
            ),
        }
    )


def enable_mock_external_api(
    app: FastAPI,
    *,
    responses: Mapping[ResponseKey, ResponseSpec] | None = None,
) -> MockRequestService:
    from api.dependencies import get_request_service  # noqa: PLC0415

    mock = MockRequestService(responses=responses or default_external_responses())
    app.dependency_overrides[get_request_service] = lambda: mock
    return mock
