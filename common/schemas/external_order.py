import json
import logging
from typing import Any

from pydantic import BaseModel, model_validator

from common.models.orders import ExternalOrderStatus

JSON_ATTRS = ("codes", "unused_codes", "broken_codes", "additional_data")

logger = logging.getLogger(__name__)


class ExternalOrder(BaseModel):
    id: int | None = None
    original_id: int
    shop_access_key: str | None = None
    amount: int | None = None
    pubg_id: int | None = None
    status: ExternalOrderStatus = ExternalOrderStatus.CREATED
    status_reason: str | None = None
    codes: dict[str, int] = {}
    unused_codes: dict[str, int] = {}
    broken_codes: list[str] = []
    redeemed_codes: list[str] = []
    additional_data: dict[str, Any] = {}
    is_only_w_codes: bool = False

    @model_validator(mode="before")
    @classmethod
    def validate_json_objs(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for attr in JSON_ATTRS:
                if data.get(attr) and isinstance(data[attr], str):
                    try:
                        data[attr] = json.loads(data[attr])
                    except json.JSONDecodeError as ex:
                        logger.exception(ex)
                        continue
        return data
