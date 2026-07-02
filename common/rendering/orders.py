import json
from collections.abc import Callable, Sequence
from decimal import Decimal

from common.models.orders import Order
from common.models.transactions import Transaction, TransactionKind
from common.money import format_money

_HISTORY_DATE_FORMAT = "%Y-%m-%d %H:%M"


def _decode_codes(codes: str | None) -> dict[str, object]:
    return json.loads(codes) if codes else {}


def render_offer_text(
    *,
    order: Order,
    full_price: Decimal,
    gettext: Callable[[str], str],
) -> str:
    return gettext("order.offer").format(
        order_id=order.public_id,
        amount=order.amount,
        full_price=format_money(full_price),
    )


def render_no_takers_text(
    *,
    order: Order,
    gettext: Callable[[str], str],
) -> str:
    return gettext("order.no_takers_moderator").format(
        order_id=order.id,
        public_id=order.public_id,
        amount=order.amount,
    )


def render_taken_text(
    *,
    order: Order,
    with_codes: bool,
    gettext: Callable[[str], str],
) -> str:
    text = gettext("order.taken").format(
        order_id=order.public_id,
        amount=order.amount,
        pubg_id=order.pubg_id,
    )
    codes = _decode_codes(order.unused_codes) if with_codes else {}
    if not codes:
        return text
    header = gettext("order.codes_header")
    line = gettext("order.codes_line")
    codes_block = "\n".join(line.format(key=key, value=value) for key, value in codes.items())
    return f"{text}\n{header}\n{codes_block}"


def render_checkin_text(*, minutes: int, gettext: Callable[[str], str]) -> str:
    return gettext("order.checkin_prompt").format(minutes=minutes)


def render_last_call_text(*, minutes: int, gettext: Callable[[str], str]) -> str:
    return gettext("order.last_call").format(minutes=minutes)


_ORDER_KEYS = {
    TransactionKind.PACK: "history.order_pack",
    TransactionKind.CODE: "history.order_code",
}
_CHILD_KEYS = {
    TransactionKind.PACK: "history.child_pack",
    TransactionKind.CODE: "history.child_code",
}


def _child_lines(*, transaction: Transaction, gettext: Callable[[str], str]) -> list[str]:
    template = gettext(_CHILD_KEYS[transaction.kind])
    if transaction.kind is TransactionKind.PACK:
        return [
            template.format(size=size, count=count) for size, count in transaction.details.items()
        ]
    return [template.format(code=code, uc=uc) for code, uc in transaction.details.items()]


def render_transaction_history(
    transactions: Sequence[Transaction],
    *,
    has_next: bool,  # noqa: ARG001
    gettext: Callable[[str], str],
) -> str:
    if not transactions:
        return gettext("history.empty")
    lines = [gettext("history.title")]
    for transaction in transactions:
        lines.append(
            gettext(_ORDER_KEYS[transaction.kind]).format(
                order_id=transaction.public_id,
                total=format_money(transaction.amount),
                date=transaction.created_at.strftime(_HISTORY_DATE_FORMAT),
            ),
        )
        lines.extend(_child_lines(transaction=transaction, gettext=gettext))
    return "\n".join(lines)
