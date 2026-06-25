from collections.abc import Sequence
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
    kind: TransactionKind
    pack_size: int | None
    code: str | None
    amount: Decimal
    created_at: datetime

    @classmethod
    def from_row(cls, row: asyncpg.Record) -> Transaction:
        return cls(
            id=row["id"],
            profile_id=row["profile_id"],
            order_id=row["order_id"],
            kind=TransactionKind(row["kind"]),
            pack_size=row["pack_size"],
            code=row["code"],
            amount=row["amount"],
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class TransactionGroup:
    order_id: int
    kind: TransactionKind
    items: list[tuple[str, Decimal]]
    total: Decimal
    created_at: datetime

    @classmethod
    def from_transactions(cls, transactions: Sequence[Transaction]) -> TransactionGroup:
        first = transactions[0]
        if first.kind is TransactionKind.PACK:
            items = [(str(line.pack_size), line.amount) for line in transactions]
        else:
            items = [(line.code or "", line.amount) for line in transactions]
        total = sum((line.amount for line in transactions), Decimal(0))
        return cls(
            order_id=first.order_id,
            kind=first.kind,
            items=items,
            total=total,
            created_at=first.created_at,
        )
