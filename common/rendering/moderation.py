import html
from datetime import time

from common.catalog.packages import format_prices
from common.catalog.tiers import Tier, tier_cap_label
from common.models.user_profiles import UserProfile

_TIME_FORMAT = "%H:%M"


def _fmt_time(value: time | None) -> str:
    return value.strftime(_TIME_FORMAT) if value is not None else "-"


def _fmt_packages(packages: tuple[int, ...] | None) -> str:
    return ", ".join(str(pkg) for pkg in packages) if packages else "-"


def _fmt_yes_no(value: bool | None) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


def _fmt_tier(tier: Tier) -> str:
    return f"{int(tier)} ({tier_cap_label(tier)})"


def render_pending_review(*, profile: UserProfile, tier: Tier) -> str:
    text = (
        "#pending user awaiting moderation\n"
        f"tg_id: {profile.tg_id}\n"
        f"works alone: {_fmt_yes_no(profile.works_alone)}\n"
        f"with codes: {_fmt_yes_no(profile.with_codes)}\n"
        f"tier: {_fmt_tier(tier)}\n"
        f"packages: {_fmt_packages(profile.packages)}\n"
        f"prices: {format_prices(profile.prices)}\n"
        f"withdrawal: {profile.withdrawal_method or '-'}\n"
        f"work hours: {_fmt_time(profile.work_start)}-{_fmt_time(profile.work_end)}"
    )
    return html.escape(text)
