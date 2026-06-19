import contextlib
from collections.abc import Iterator
from contextlib import AbstractContextManager

from aiogram.exceptions import TelegramBadRequest

_NOT_MODIFIED = ("message is not modified",)
_MESSAGE_GONE = ("message to delete not found", "message can't be deleted")


@contextlib.contextmanager
def _ignore_bad_request(reasons: tuple[str, ...]) -> Iterator[None]:
    try:
        yield
    except TelegramBadRequest as error:
        if not any(reason in error.message for reason in reasons):
            raise


def ignore_not_modified() -> AbstractContextManager[None]:
    return _ignore_bad_request(_NOT_MODIFIED)


def ignore_message_gone() -> AbstractContextManager[None]:
    return _ignore_bad_request(_MESSAGE_GONE)
