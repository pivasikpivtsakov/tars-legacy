import html
from datetime import time

from aiogram.utils.i18n import gettext as _

from common.catalog.packages import format_prices
from common.catalog.tiers import Tier
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


def render_pending_review(*, profile: UserProfile, with_codes: bool, tier: Tier) -> str:
    lines = [
        "#pending user awaiting moderation",
        f"tg_id: {profile.tg_id}",
        f"chat addable: {_fmt_yes_no(profile.chat_addable)}",
        f"with codes: {_fmt_yes_no(with_codes)}",
        f"tier: {tier.range_label()}",
    ]
    if not with_codes:
        lines.append(f"packages: {_fmt_packages(profile.packages)}")
        lines.append(f"prices: {format_prices(profile.prices)}")
    lines.append(f"withdrawal: {profile.withdrawal_method or '-'}")
    lines.append(f"work hours: {_fmt_time(profile.work_start)}-{_fmt_time(profile.work_end)}")
    text = html.escape("\n".join(lines))
    if with_codes != profile.with_codes:
        text = f"{text}\n{html.escape(_('moderation.with_codes_changed'))}"
    return text
