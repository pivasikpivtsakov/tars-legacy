import json
from datetime import UTC, datetime
from decimal import Decimal

from common.models.transactions import Transaction, TransactionKind
from common.rendering.orders import render_transaction_history

_AT = datetime(2024, 1, 2, 15, 30, tzinfo=UTC)

_STRINGS = {
    "history.title": "History:",
    "history.empty": "Empty",
    "history.order_pack": "PACK #{order_id} +{total} {date}",
    "history.order_code": "CODE #{order_id} +{total} {date}",
    "history.child_pack": "  {size} x{count}",
    "history.child_code": "  {code} ({uc})",
}


def _gettext(key: str) -> str:
    return _STRINGS[key]


def _txn(
    *,
    order_id: int,
    kind: TransactionKind,
    amount: Decimal,
    details: dict[str, int],
) -> Transaction:
    return Transaction(
        id=0,
        profile_id=1,
        order_id=order_id,
        kind=kind,
        amount=amount,
        details=details,
        created_at=_AT,
    )


def test_from_row_parses_details_json() -> None:
    row = {
        "id": 3,
        "profile_id": 1,
        "order_id": 9,
        "kind": "code",
        "amount": Decimal("1.00"),
        "details": json.dumps({"CODE-1": 60, "CODE-2": 325}),
        "created_at": _AT,
    }

    transaction = Transaction.from_row(row)

    assert transaction.kind is TransactionKind.CODE
    assert transaction.amount == Decimal("1.00")
    assert transaction.details == {"CODE-1": 60, "CODE-2": 325}


def test_render_transaction_history_empty() -> None:
    assert render_transaction_history([], has_next=False, gettext=_gettext) == "Empty"


def test_render_transaction_history_pack_and_code_tree() -> None:
    pack = _txn(
        order_id=7,
        kind=TransactionKind.PACK,
        amount=Decimal("50.00"),
        details={"325": 1, "60": 1},
    )
    code = _txn(
        order_id=9,
        kind=TransactionKind.CODE,
        amount=Decimal("1.00"),
        details={"CODE-1": 60, "CODE-2": 325},
    )

    rendered = render_transaction_history([pack, code], has_next=False, gettext=_gettext)

    assert rendered == (
        "History:\n"
        "PACK #7 +50.00 2024-01-02 15:30\n"
        "  325 x1\n"
        "  60 x1\n"
        "CODE #9 +1.00 2024-01-02 15:30\n"
        "  CODE-1 (60)\n"
        "  CODE-2 (325)"
    )
