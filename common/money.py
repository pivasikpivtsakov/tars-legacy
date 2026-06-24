import re
from decimal import Decimal

MONEY_QUANT = Decimal("0.01")

_MONEY_RE = re.compile(r"\d+(\.\d{1,2})?")


def parse_money(raw: str) -> Decimal | None:
    text = raw.strip()
    if not _MONEY_RE.fullmatch(text):
        return None
    return Decimal(text).quantize(MONEY_QUANT)


def to_money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(MONEY_QUANT)


def format_money(value: Decimal) -> str:
    return f"{value:.2f}"


def to_minor_units(value: Decimal) -> int:
    return int((value * 100).to_integral_value())


def from_minor_units(value: int) -> Decimal:
    return (Decimal(value) / 100).quantize(MONEY_QUANT)
