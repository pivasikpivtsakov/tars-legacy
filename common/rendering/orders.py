import json
from collections.abc import Callable, Sequence
from decimal import Decimal

from common.models.orders import Order
from common.models.transactions import TransactionGroup, TransactionKind
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
        order_id=order.id,
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
        amount=order.amount,
    )


def render_taken_text(
    *,
    order: Order,
    with_codes: bool,
    gettext: Callable[[str], str],
) -> str:
    text = gettext("order.taken").format(
        order_id=order.id,
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


def _history_items(group: TransactionGroup) -> str:
    if group.kind is TransactionKind.PACK:
        return ", ".join(label for label, _amount in group.items)
    return ", ".join(f"{label} ({int(amount)})" for label, amount in group.items)


def render_transaction_history(
    groups: Sequence[TransactionGroup],
    *,
    has_next: bool,  # noqa: ARG001
    gettext: Callable[[str], str],
) -> str:
    if not groups:
        return gettext("history.empty")
    line_keys = {
        TransactionKind.PACK: "history.line_pack",
        TransactionKind.CODE: "history.line_code",
    }
    lines = [gettext("history.title")]
    lines.extend(
        gettext(line_keys[group.kind]).format(
            items=_history_items(group),
            total=format_money(group.total),
            date=group.created_at.strftime(_HISTORY_DATE_FORMAT),
        )
        for group in groups
    )
    return "\n".join(lines)
