from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from common.catalog.tiers import Tier, tier_cap_label

_CODES_ON = "\u2611 with codes"
_CODES_OFF = "\u2610 with codes"
_EDIT_PACKS = "edit packs"
_APPROVE = "approve"
_DECLINE = "decline"
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
