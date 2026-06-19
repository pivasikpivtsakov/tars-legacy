import json
from collections.abc import Callable

from common.models.orders import Order


def _decode_codes(codes: str | None) -> dict[str, object]:
    return json.loads(codes) if codes else {}


def render_offer_text(
    *,
    order: Order,
    full_price: int,
    gettext: Callable[[str], str],
) -> str:
    return gettext("order.offer").format(
        order_id=order.id,
        amount=order.amount,
        full_price=full_price,
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
    codes = _decode_codes(order.codes) if with_codes else {}
    if not codes:
        return text
    header = gettext("order.codes_header")
    line = gettext("order.codes_line")
    codes_block = "\n".join(line.format(key=key, value=value) for key, value in codes.items())
    return f"{text}\n{header}\n{codes_block}"
