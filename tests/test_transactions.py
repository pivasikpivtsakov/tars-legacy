from datetime import UTC, datetime
from decimal import Decimal

from common.models.transactions import Transaction, TransactionGroup, TransactionKind
from common.rendering.orders import render_transaction_history

_FIRST_AT = datetime(2024, 1, 2, 15, 30, tzinfo=UTC)
_LATER_AT = datetime(2024, 1, 2, 16, 0, tzinfo=UTC)

_STRINGS = {
    "history.title": "History:",
    "history.empty": "Empty",
    "history.line_pack": "PACK {items} +{total} {date}",
    "history.line_code": "CODE {items} +{total} {date}",
}


def _gettext(key: str) -> str:
    return _STRINGS[key]


def _txn(
    *,
    order_id: int,
    kind: TransactionKind,
    amount: Decimal,
    pack_size: int | None = None,
    code: str | None = None,
    created_at: datetime = _FIRST_AT,
) -> Transaction:
    return Transaction(
        id=0,
        profile_id=1,
        order_id=order_id,
        kind=kind,
        pack_size=pack_size,
        code=code,
        amount=amount,
        created_at=created_at,
    )


def test_pack_group_collapses_rows_into_one_entry() -> None:
    order_id = 7
    group = TransactionGroup.from_transactions(
        [
            _txn(
                order_id=order_id,
                kind=TransactionKind.PACK,
                pack_size=325,
                amount=Decimal("40.00"),
            ),
            _txn(
                order_id=order_id,
                kind=TransactionKind.PACK,
                pack_size=60,
                amount=Decimal("10.00"),
                created_at=_LATER_AT,
            ),
        ],
    )

    assert group.kind is TransactionKind.PACK
    assert group.order_id == order_id
    assert group.items == [("325", Decimal("40.00")), ("60", Decimal("10.00"))]
    assert group.total == Decimal("50.00")
    assert group.created_at == _FIRST_AT


def test_code_group_collapses_rows_into_one_entry() -> None:
    group = TransactionGroup.from_transactions(
        [
            _txn(order_id=9, kind=TransactionKind.CODE, code="CODE-1", amount=Decimal(60)),
            _txn(order_id=9, kind=TransactionKind.CODE, code="CODE-2", amount=Decimal(325)),
        ],
    )

    assert group.kind is TransactionKind.CODE
    assert group.items == [("CODE-1", Decimal(60)), ("CODE-2", Decimal(325))]
    assert group.total == Decimal(385)


def test_render_transaction_history_empty() -> None:
    assert render_transaction_history([], has_next=False, gettext=_gettext) == "Empty"


def test_render_transaction_history_pack_and_code() -> None:
    pack_group = TransactionGroup.from_transactions(
        [
            _txn(order_id=7, kind=TransactionKind.PACK, pack_size=325, amount=Decimal("40.00")),
            _txn(order_id=7, kind=TransactionKind.PACK, pack_size=60, amount=Decimal("10.00")),
        ],
    )
    code_group = TransactionGroup.from_transactions(
        [
            _txn(order_id=9, kind=TransactionKind.CODE, code="CODE-1", amount=Decimal(60)),
            _txn(order_id=9, kind=TransactionKind.CODE, code="CODE-2", amount=Decimal(325)),
        ],
    )

    rendered = render_transaction_history(
        [pack_group, code_group],
        has_next=False,
        gettext=_gettext,
    )

    assert rendered == (
        "History:\n"
        "PACK 325, 60 +50.00 2024-01-02 15:30\n"
        "CODE CODE-1 (60), CODE-2 (325) +385.00 2024-01-02 15:30"
    )
