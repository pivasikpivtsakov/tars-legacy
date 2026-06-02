from collections.abc import Callable

from common.models.orders import Order


def append_codes_line(
    *,
    text: str,
    order: Order,
    with_codes: bool,
    gettext: Callable[[str], str],
) -> str:
    if not (with_codes and order.codes):
        return text
    codes = order.codes
    joined = ", ".join(str(code) for code in codes) if isinstance(codes, list) else str(codes)
    codes_line = gettext("order.codes_line").format(codes=joined)
    return f"{text}\n{codes_line}"


def render_offer_text(
    *,
    order: Order,
    full_price: int,
    with_codes: bool,
    gettext: Callable[[str], str],
) -> str:
    text = gettext("order.offer").format(
        order_id=order.id,
        amount=order.amount,
        full_price=full_price,
    )
    return append_codes_line(
        text=text,
        order=order,
        with_codes=with_codes,
        gettext=gettext,
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
    return append_codes_line(
        text=text,
        order=order,
        with_codes=with_codes,
        gettext=gettext,
    )
