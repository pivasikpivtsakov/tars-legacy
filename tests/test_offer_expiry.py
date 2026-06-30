import asyncio
from collections.abc import Sequence

from common.repositories.redis.offer_deadlines import OfferDeadline
from common.services.offer_expiry import OfferExpiryService


class _FakeOffers:
    def __init__(self, *, expired: list[tuple[int, int]]) -> None:
        self._expired = list(expired)
        self.expire_many_calls: list[list[tuple[int, int]]] = []

    async def expire_many(
        self,
        *,
        offers: Sequence[tuple[int, int]],
    ) -> list[tuple[int, int]]:
        self.expire_many_calls.append(list(offers))
        return list(self._expired)


class _FakeRating:
    def __init__(self) -> None:
        self.not_taken: list[list[int]] = []

    async def record_not_taken(self, *, user_ids: Sequence[int]) -> None:
        self.not_taken.append(list(user_ids))


class _FakePending:
    def __init__(self) -> None:
        self.released_many: list[list[int]] = []

    async def release_many(self, *, user_ids: Sequence[int]) -> None:
        self.released_many.append(list(user_ids))


class _FakeBot:
    def __init__(self) -> None:
        self.edits: list[tuple[int, int, str]] = []

    async def edit_message_text(
        self,
        *,
        text: str,
        chat_id: int,
        message_id: int,
        reply_markup: object,
    ) -> None:
        self.edits.append((chat_id, message_id, text))
        assert reply_markup is None


class _FakeDispatch:
    def __init__(self) -> None:
        self.requests = 0

    async def request(self) -> None:
        self.requests += 1


def _deadline(*, order_id: int, user_id: int) -> OfferDeadline:
    return OfferDeadline(
        order_id=order_id,
        user_id=user_id,
        chat_id=order_id * 10,
        message_id=order_id * 100,
        expired_text=f"expired-{order_id}",
    )


def _run(
    *,
    offers: _FakeOffers,
    rating: _FakeRating,
    pending: _FakePending,
    bot: _FakeBot,
    dispatch: _FakeDispatch,
    deadlines: Sequence[OfferDeadline],
) -> None:
    service = OfferExpiryService(
        offers=offers,
        rating=rating,
        pending=pending,
        bot=bot,
        dispatch=dispatch,
    )
    asyncio.run(service.expire_offers(deadlines=deadlines))


def test_expire_offers_batches_release_and_wakes_once() -> None:
    offers = _FakeOffers(expired=[(1, 11), (2, 22)])
    rating = _FakeRating()
    pending = _FakePending()
    bot = _FakeBot()
    dispatch = _FakeDispatch()
    deadlines = [_deadline(order_id=1, user_id=11), _deadline(order_id=2, user_id=22)]

    _run(
        offers=offers,
        rating=rating,
        pending=pending,
        bot=bot,
        dispatch=dispatch,
        deadlines=deadlines,
    )

    assert offers.expire_many_calls == [[(1, 11), (2, 22)]]  # single batched update
    assert rating.not_taken == [[11, 22]]  # one pipeline
    assert pending.released_many == [[11, 22]]  # one release call
    assert dispatch.requests == 1  # single wake, not one per offer
    assert sorted(bot.edits) == [(10, 100, "expired-1"), (20, 200, "expired-2")]


def test_expire_offers_only_acts_on_rows_actually_expired() -> None:
    offers = _FakeOffers(expired=[(1, 11)])  # order 2 was taken meanwhile
    rating = _FakeRating()
    pending = _FakePending()
    bot = _FakeBot()
    dispatch = _FakeDispatch()
    deadlines = [_deadline(order_id=1, user_id=11), _deadline(order_id=2, user_id=22)]

    _run(
        offers=offers,
        rating=rating,
        pending=pending,
        bot=bot,
        dispatch=dispatch,
        deadlines=deadlines,
    )

    assert rating.not_taken == [[11]]
    assert pending.released_many == [[11]]
    assert dispatch.requests == 1
    assert bot.edits == [(10, 100, "expired-1")]  # only the genuinely expired offer


def test_expire_offers_noop_when_nothing_expired() -> None:
    offers = _FakeOffers(expired=[])
    rating = _FakeRating()
    pending = _FakePending()
    bot = _FakeBot()
    dispatch = _FakeDispatch()
    deadlines = [_deadline(order_id=1, user_id=11)]

    _run(
        offers=offers,
        rating=rating,
        pending=pending,
        bot=bot,
        dispatch=dispatch,
        deadlines=deadlines,
    )

    assert offers.expire_many_calls == [[(1, 11)]]
    assert rating.not_taken == []
    assert pending.released_many == []
    assert dispatch.requests == 0
    assert bot.edits == []


def test_expire_offers_empty_batch_skips_db() -> None:
    offers = _FakeOffers(expired=[])
    rating = _FakeRating()
    pending = _FakePending()
    bot = _FakeBot()
    dispatch = _FakeDispatch()

    _run(offers=offers, rating=rating, pending=pending, bot=bot, dispatch=dispatch, deadlines=[])

    assert offers.expire_many_calls == []  # don't even hit the DB on an empty poll
    assert dispatch.requests == 0
