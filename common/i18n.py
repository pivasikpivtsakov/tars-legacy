import os
from pathlib import Path

from aiogram.utils.i18n import I18n

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DOMAIN = "bot"


def build_i18n() -> I18n:
    return I18n(
        path=LOCALES_DIR,
        default_locale=os.environ.get("DEFAULT_LOCALE", "en"),
        domain=DOMAIN,
    )
