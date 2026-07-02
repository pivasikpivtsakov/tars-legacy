import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

import asyncpg


class TransactionKind(StrEnum):
    PACK = "pack"
    CODE = "code"


@dataclass(frozen=True, slots=True)
class Transaction:
    id: int
    profile_id: int
    order_id: int
    public_id: str
    kind: TransactionKind
    amount: Decimal
    details: dict[str, int]
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> Transaction:
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            order_id=row["order_id"],
            public_id=row["public_id"],
            kind=TransactionKind(row["kind"]),
            amount=row["amount"],
            details=json.loads(row["details"]),
            created_at=row["created_at"],
        )
