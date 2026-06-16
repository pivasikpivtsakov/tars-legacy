from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_user_id: ContextVar[int | None] = ContextVar("log_user_id", default=None)
_update_id: ContextVar[int | None] = ContextVar("log_update_id", default=None)


def current_user_id() -> int | None:
    return _user_id.get()


def current_update_id() -> int | None:
    return _update_id.get()


@contextmanager
def log_context(*, user_id: int | None, update_id: int | None) -> Iterator[None]:
    user_token = _user_id.set(user_id)
    update_token = _update_id.set(update_id)
    try:
        yield
    finally:
        _user_id.reset(user_token)
        _update_id.reset(update_token)
