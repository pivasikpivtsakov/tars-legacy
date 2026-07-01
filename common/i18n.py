import functools
import os
from collections.abc import Callable
from pathlib import Path

from aiogram.utils.i18n import I18n

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DOMAIN = "bot"

LOCALE_FSM_KEY = "locale"
LANGUAGE_NAMES: dict[str, str] = {"en": "English", "ru": "Русский"}


def build_i18n() -> I18n:
    return I18n(
        path=LOCALES_DIR,
        default_locale=os.environ.get("DEFAULT_LOCALE", "en"),
        domain=DOMAIN,
    )


i18n = build_i18n()


def gettext_for(locale: str) -> Callable[[str], str]:
    return functools.partial(i18n.gettext, locale=locale)
