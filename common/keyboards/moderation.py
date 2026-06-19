from collections.abc import Iterable

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.catalog.packages import PACKAGE_SIZES
from common.catalog.tiers import Tier, tier_cap_label
from common.keyboards.packages import package_toggle_rows

_CODES_ON = "\u2611 with codes"
_CODES_OFF = "\u2610 with codes"
_EDIT_PACKS = "edit packs"
_APPROVE = "approve"
_DECLINE = "decline"
_SAVE = "save"
_CANCEL = "cancel"
_TIER_SELECTED = "\u25c9"
_TIER_UNSELECTED = "\u25cb"


class ModApproveCB(CallbackData, prefix="mod_ok"):
    profile_id: int
    with_codes: bool
    tier: int


class ModDenyCB(CallbackData, prefix="mod_no"):
    profile_id: int


class ModToggleCodesCB(CallbackData, prefix="mod_codes"):
    profile_id: int
    with_codes: bool
    tier: int


class ModSetTierCB(CallbackData, prefix="mod_tier"):
    profile_id: int
    with_codes: bool
    tier: int


class ModEditPacksCB(CallbackData, prefix="mod_packs"):
    profile_id: int
    with_codes: bool
    tier: int


class ModPackToggleCB(CallbackData, prefix="mod_pkg"):
    profile_id: int
    with_codes: bool
    tier: int
    mask: int
    idx: int


class ModPacksSaveCB(CallbackData, prefix="mod_pkg_ok"):
    profile_id: int
    with_codes: bool
    tier: int
    mask: int


class ModPacksCancelCB(CallbackData, prefix="mod_pkg_no"):
    profile_id: int
    with_codes: bool
    tier: int


def packages_to_mask(packages: Iterable[int]) -> int:
    index = {size: i for i, size in enumerate(PACKAGE_SIZES)}
    mask = 0
    for size in packages:
        mask |= 1 << index[size]
    return mask


def mask_to_packages(mask: int) -> list[int]:
    return [size for i, size in enumerate(PACKAGE_SIZES) if mask & (1 << i)]


def _tier_choice_row(
    *,
    profile_id: int,
    with_codes: bool,
    tier: int,
) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=f"{_TIER_SELECTED if int(option) == tier else _TIER_UNSELECTED} "
            f"{tier_cap_label(option)}",
            callback_data=ModSetTierCB(
                profile_id=profile_id,
                with_codes=with_codes,
                tier=int(option),
            ).pack(),
        )
        for option in Tier
    ]


def moderation_decision_kb(
    *,
    profile_id: int,
    with_codes: bool,
    tier: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_CODES_ON if with_codes else _CODES_OFF,
                    callback_data=ModToggleCodesCB(
                        profile_id=profile_id,
                        with_codes=with_codes,
                        tier=tier,
                    ).pack(),
                ),
            ],
            _tier_choice_row(profile_id=profile_id, with_codes=with_codes, tier=tier),
            [
                InlineKeyboardButton(
                    text=_EDIT_PACKS,
                    callback_data=ModEditPacksCB(
                        profile_id=profile_id,
                        with_codes=with_codes,
                        tier=tier,
                    ).pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=_APPROVE,
                    callback_data=ModApproveCB(
                        profile_id=profile_id,
                        with_codes=with_codes,
                        tier=tier,
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=_DECLINE,
                    callback_data=ModDenyCB(profile_id=profile_id).pack(),
                ),
            ],
        ],
    )


def moderation_packages_kb(
    *,
    profile_id: int,
    with_codes: bool,
    tier: int,
    mask: int,
) -> InlineKeyboardMarkup:
    size_to_idx = {size: i for i, size in enumerate(PACKAGE_SIZES)}
    rows = package_toggle_rows(
        selected=mask_to_packages(mask),
        callback_factory=lambda size: ModPackToggleCB(
            profile_id=profile_id,
            with_codes=with_codes,
            tier=tier,
            mask=mask,
            idx=size_to_idx[size],
        ).pack(),
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=_SAVE,
                callback_data=ModPacksSaveCB(
                    profile_id=profile_id,
                    with_codes=with_codes,
                    tier=tier,
                    mask=mask,
                ).pack(),
            ),
            InlineKeyboardButton(
                text=_CANCEL,
                callback_data=ModPacksCancelCB(
                    profile_id=profile_id,
                    with_codes=with_codes,
                    tier=tier,
                ).pack(),
            ),
        ],
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
