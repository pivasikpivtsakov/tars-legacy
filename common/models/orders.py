from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

import asyncpg


class OrderStatus(StrEnum):
    PENDING = "pending"
    OFFERING = "offering"
    TAKEN = "taken"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_TAKERS = "no_takers"


class ExternalOrderStatus(StrEnum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    MANUAL_PROCESSING = "MANUAL_PROCESSING"
    RESTART = "RESTART"
    PENDING = "PENDING"
    DEFERRED = "DEFERRED"
    FAILED = "FAILED"
    REDEEMED = "REDEEMED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class Order:
    id: int
    original_id: int
    shop_access_key: str | None
    status: OrderStatus
    status_reason: str | None
    amount: int
    pubg_id: int | None
    codes: Any
    unused_codes: Any
    broken_codes: tuple[str, ...]
    redeemed_codes: tuple[str, ...]
    additional_data: Any
    offered_at: datetime | None
    closed_at: datetime | None
    taken_at: datetime | None
    taken_by: int | None
    taken_price: int | None
    created_at: datetime
    updated_at: datetime
    external_status: ExternalOrderStatus

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> Order:
        return cls(
            id=row["id"],
            original_id=row["original_id"],
            shop_access_key=row["shop_access_key"],
            status=OrderStatus(row["status"]),
            status_reason=row["status_reason"],
            amount=row["amount"],
            pubg_id=row["pubg_id"],
            codes=row["codes"],
            unused_codes=row["unused_codes"],
            broken_codes=tuple(row["broken_codes"]),
            redeemed_codes=tuple(row["redeemed_codes"]),
            additional_data=row["additional_data"],
            offered_at=row["offered_at"],
            closed_at=row["closed_at"],
            taken_at=row["taken_at"],
            taken_by=row["taken_by"],
            taken_price=row["taken_price"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            external_status=ExternalOrderStatus(row["external_status"]),
        )
