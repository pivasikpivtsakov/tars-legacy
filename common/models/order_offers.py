from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

import asyncpg


class OrderOfferStatus(StrEnum):
    OFFERED = "offered"
    TAKEN = "taken"
    DECLINED = "declined"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class OrderOffer:
    order_id: int
    user_id: int
    status: OrderOfferStatus
    offered_at: datetime
    resolved_at: datetime | None

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> OrderOffer:
        return cls(
            order_id=row["order_id"],
            user_id=row["user_id"],
            status=OrderOfferStatus(row["status"]),
            offered_at=row["offered_at"],
            resolved_at=row["resolved_at"],
        )
