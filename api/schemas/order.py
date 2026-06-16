import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from common.models.orders import ExternalOrderStatus, OrderStatus


class OrderCreate(BaseModel):
    id: int
    pubg_id: int  # было none
    shop_access_key: str | None = None
    amount: int | None = None
    status: ExternalOrderStatus = ExternalOrderStatus.CREATED
    status_reason: str | None = None
    codes: dict[str, int] = {}
    unused_codes: dict[str, int] = {}
    broken_codes: list[str] = []
    redeemed_codes: list[str] = []
    additional_data: dict[str, Any] = {}


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_id: int
    shop_access_key: str | None = None
    status: OrderStatus
    external_status: ExternalOrderStatus | None = None
    status_reason: str | None = None
    amount: int
    pubg_id: int | None = None
    codes: dict[str, int] | None = None
    unused_codes: dict[str, int] | None = None
    broken_codes: list[str] = []
    redeemed_codes: list[str] = []
    additional_data: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("codes", "unused_codes", "additional_data", mode="before")
    @classmethod
    def decode_json(cls, value: Any) -> Any:
        if isinstance(value, str):
            return json.loads(value)
        return value
