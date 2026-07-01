from aiogram.utils.i18n import gettext as _


def reply_text_matches(text: str, *keys: str) -> bool:
    return text in {_(key) for key in keys}
