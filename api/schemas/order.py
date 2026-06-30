import json
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from common.models.orders import ExternalOrderStatus, OrderStatus
from common.schemas.external_order import BoundedVarchar


class OrderCreate(BaseModel):
    id: int
    merchant_id: str

    shop_id: int
    shop_name: str
    shop_access_key: BoundedVarchar
    shop_access_key_name: str

    order_type: str
    activator_type: str

    amount: int
    decomposed_amount: list[int]
    pubg_id: int

    status: ExternalOrderStatus = ExternalOrderStatus.CREATED
    status_reason: BoundedVarchar | None = None

    redeem_attempts: int = 2
    max_redeem_attempts: int = 5
    ignore_redeem_error: bool = False

    codes: dict[str, int] = {}
    unused_codes: dict[str, int] = {}
    broken_codes: list[BoundedVarchar] = []
    redeemed_codes: list[BoundedVarchar] = []

    screenshots: list[str] = []
    webhook: str | None = None
    additional_data: dict[str, Any] = {}

    last_update: datetime
    creation_date: date
    creation_timestamp: datetime

    is_only_w_codes: bool


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
