from collections.abc import Mapping
from typing import Any

import httpx

from common.environment import MOCK_EXTERNAL_API
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

MOCK_ORDER_AMOUNT = 660
MOCK_CODE = "WWTucFsS2f2956Y6wb"
MOCK_PUBG_ID = 52089941242
MOCK_PLAYER_OPEN_ID = 113506024664991016
MOCK_FRAUD_OPEN_ID = 999999999999999
MOCK_REPLACEMENT_CODE = "RPLCa1B2c3D4e5F6g7"
MOCK_NEW_CODE = "NEWa1B2c3D4e5F6g7h8"


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
    is_redeemed: bool = False,
    exchange_open_id: int = MOCK_PLAYER_OPEN_ID,
    amount: int = MOCK_ORDER_AMOUNT,
) -> ResponseSpec:
    return (
        200,
        {
            "is_redeemed": is_redeemed,
            "exchange_open_id": exchange_open_id,
            "amount": amount,
        },
    )


def _mock_additional_data(*, player_open_id: int = MOCK_PLAYER_OPEN_ID) -> dict[str, Any]:
    return {
        "order_id": 12197219,
        "merchant_order_id": 1782821152914623,
        "order_uuid": "019f186b-e892-7522-b10f-9462bf652bf7",
        "user_id": None,
        "bot_name": "karat",
        "product_name": "660UC",
        "bot_id": 22,
        "discount_reason": "",
        "payment_method": "payin",
        "price": 769,
        "currency": "RUB",
        "redeem_sessions_count": 1,
        "broken_code_add_date": None,
        "broken_code_add_info": None,
        "providers": ["TS-A"],
        "debug_messages": [
            "[TS-A] Аккаунт griffinnolanjuig@outlook.com был прогрет заранее",
            f"[TS-A] fp-behv для кода {MOCK_CODE} был прогрет заранее",
            f"Code exchanged successfully: {MOCK_CODE}",
        ],
        "debug_screenshots": [],
        "codes_product_ids": {MOCK_CODE: "600_coins_redeem_vip"},
        "trust_code": True,
        "selected_activator_server": (
            "http://midas-exchanger-api-exchanger-3:14200/midas-server/v2"
        ),
        "midas_accounts": ["griffinnolanjuig@outlook.com:S33A6SX5123AdS"],
        "midas_order_info": [],
        "player_open_id": player_open_id,
        "safe_restart": True,
        "activation_time_seconds": 28.311,
        "provider_timings": [{"provider": "TS-A", "duration_seconds": 28.311}],
        "is_manual_redeem": False,
    }


def order_get_response(
    *,
    codes: Mapping[str, int] | None = None,
    unused_codes: Mapping[str, int] | None = None,
    status: ExternalOrderStatus = ExternalOrderStatus.PENDING,
    status_reason: str | None = None,
    player_open_id: int = MOCK_PLAYER_OPEN_ID,
) -> ResponseSpec:
    code_map = {MOCK_CODE: MOCK_ORDER_AMOUNT} if codes is None else dict(codes)
    unused = dict(code_map if unused_codes is None else unused_codes)
    return (
        200,
        {
            "id": 326776,
            "merchant_id": "1782821152914623",
            "shop_id": 7,
            "shop_name": "LONG BOT",
            "shop_access_key": "mock-shop-access-key",
            "shop_access_key_name": "Midas API V3",
            "order_type": "REDEEM",
            "activator_type": "API",
            "amount": MOCK_ORDER_AMOUNT,
            "decomposed_amount": None,
            "pubg_id": MOCK_PUBG_ID,
            "status": status,
            "status_reason": status_reason,
            "redeem_attempts": 1,
            "max_redeem_attempts": 2,
            "ignore_redeem_error": False,
            "codes": code_map,
            "unused_codes": unused,
            "broken_codes": [],
            "redeemed_codes": [],
            "screenshots": [],
            "webhook": None,
            "additional_data": _mock_additional_data(player_open_id=player_open_id),
            "last_update": "2026-06-30T15:23:14.705522",
            "creation_date": "2026-06-30",
            "creation_timestamp": "2026-06-30T15:06:29.989030",
        },
    )


def default_external_responses(
    *,
    overrides: Mapping[ResponseKey, ResponseSpec] | None = None,
) -> dict[ResponseKey, ResponseSpec]:
    responses: dict[ResponseKey, ResponseSpec] = {
        (PATH_ORDER_GET, MethodsEnum.GET): order_get_response(),
        (PATH_ORDERS_SET_STATUS, MethodsEnum.PATCH): (200, {"success": True}),
        (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(),
        (PATH_CODE_EXCHANGE_STATUS, MethodsEnum.GET): (
            200,
            {"is_redeemed": True, "exchange_open_id": MOCK_PLAYER_OPEN_ID},
        ),
        (PATH_CODES_SET_STATUS, MethodsEnum.PATCH): (200, {"success": True}),
        (PATH_CODES_REPLACE, MethodsEnum.POST): (200, {"code": MOCK_REPLACEMENT_CODE}),
        (PATH_CODES_GET, MethodsEnum.GET): (200, [{"code": MOCK_NEW_CODE}]),
        (PATH_ORDER_COMPLETE, MethodsEnum.PATCH): (200, {"success": True}),
        (PATH_ORDER_UPDATE_CODES, MethodsEnum.PUT): (200, {"success": True}),
        (PATH_SEND_MSG_TO_MODERATORS, MethodsEnum.POST): (200, {"success": True}),
    }
    if overrides:
        responses.update(overrides)
    return responses


def success_external_responses() -> dict[ResponseKey, ResponseSpec]:
    """Code redeemed by the right player -> order passes the anti-fraud finished check."""
    return default_external_responses(
        overrides={
            (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(
                is_redeemed=True
            ),
        }
    )


def fraud_external_responses(
    *,
    exchange_open_id: int = MOCK_FRAUD_OPEN_ID,
) -> dict[ResponseKey, ResponseSpec]:
    """Code redeemed on a different open_id -> antifraud blocks the user."""
    return default_external_responses(
        overrides={
            (PATH_CODE_EXCHANGE_TIME, MethodsEnum.GET): code_exchange_time_response(
                is_redeemed=True,
                exchange_open_id=exchange_open_id,
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


def build_request_service(
    *,
    responses: Mapping[ResponseKey, ResponseSpec],
) -> RequestService:
    """Return canned responses when MOCK_EXTERNAL_API is set, otherwise a real client."""
    if MOCK_EXTERNAL_API:
        return MockRequestService(responses=responses)
    return RequestService()
