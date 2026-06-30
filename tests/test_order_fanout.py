import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from common.models.orders import Order, OrderStatus
from common.services.order_fanout import OrderFanoutService
from common.services.ranking import RankedCandidate


def _order(*, status: OrderStatus, order_id: int = 1) -> Order:
    now = datetime.now(UTC)
    return Order(
        id=order_id,
        original_id=1,
        shop_access_key=None,
        status=status,
        status_reason=None,
        refusal_reason=None,
        amount=60,
        pubg_id=None,
        codes=None,
        unused_codes=None,
        broken_codes=(),
        redeemed_codes=(),
        additional_data=None,
        offered_at=None,
        closed_at=None,
        taken_at=None,
        taken_by=None,
        taken_price=None,
        created_at=now,
        updated_at=now,
        external_status=None,
        is_only_w_codes=False,
    )


class _FakeOffers:
    def __init__(
        self,
        *,
        expire_one: int | None = None,
        expire_offered_for_orders: list[tuple[int, int]] | None = None,
        offered_user_ids_many: dict[int, set[int]] | None = None,
    ) -> None:
        self._expire_one = expire_one
        self._expire_offered_for_orders = list(expire_offered_for_orders or [])
        self._offered_user_ids_many = dict(offered_user_ids_many or {})
        self.expire_one_calls: list[tuple[int, int]] = []
        self.expire_offered_for_orders_calls: list[list[int]] = []
        self.offered_user_ids_many_calls: list[list[int]] = []
        self.record_offer_calls: list[tuple[int, int]] = []

    async def expire_one(self, *, order_id: int, user_id: int) -> int | None:
        self.expire_one_calls.append((order_id, user_id))
        return self._expire_one

    async def expire_offered_for_orders(
        self,
        *,
        order_ids: Sequence[int],
    ) -> list[tuple[int, int]]:
        self.expire_offered_for_orders_calls.append(list(order_ids))
        return list(self._expire_offered_for_orders)

    async def offered_user_ids_many(self, *, order_ids: Sequence[int]) -> dict[int, set[int]]:
        self.offered_user_ids_many_calls.append(list(order_ids))
        return {
            order_id: set(user_ids)
            for order_id, user_ids in self._offered_user_ids_many.items()
        }

    async def record_offer(self, *, order_id: int, user_id: int) -> None:
        self.record_offer_calls.append((order_id, user_id))


class _FakeRating:
    def __init__(self) -> None:
        self.not_taken: list[list[int]] = []

    async def record_not_taken(self, *, user_ids: list[int]) -> None:
        self.not_taken.append(list(user_ids))


class _FakePending:
    def __init__(self, *, reserve: bool = True) -> None:
        self._reserve = reserve
        self.released_many: list[list[int]] = []
        self.released: list[int] = []
        self.reserved: list[tuple[int, int]] = []

    async def reserve(self, *, user_id: int, limit: int) -> bool:
        self.reserved.append((user_id, limit))
        return self._reserve

    async def release(self, *, user_id: int) -> None:
        self.released.append(user_id)

    async def release_many(self, *, user_ids: list[int]) -> None:
        self.released_many.append(list(user_ids))


class _FakeOrders:
    def __init__(self, *, due: list[Order] | None = None) -> None:
        self._due = list(due or [])
        self.due_calls: list[tuple[int, int]] = []
        self.mark_no_takers_calls: list[int] = []
        self.mark_offering_calls: list[int] = []

    async def list_due_for_fanout(self, *, stale_after_seconds: int, limit: int) -> list[Order]:
        self.due_calls.append((stale_after_seconds, limit))
        return list(self._due)

    async def mark_no_takers(self, *, order_id: int) -> None:
        self.mark_no_takers_calls.append(order_id)

    async def mark_offering(self, *, order_id: int) -> None:
        self.mark_offering_calls.append(order_id)


class _FakeBot:
    def __init__(self, *, message_id: int = 100) -> None:
        self._message_id = message_id
        self.sent: list[int] = []

    async def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        reply_markup: object = None,
    ) -> object:
        self.sent.append(chat_id)
        assert text
        return SimpleNamespace(message_id=self._message_id)


class _FakeProfiles:
    def __init__(
        self,
        *,
        tg_id: int | None,
        tg_ids: dict[int, int] | None = None,
    ) -> None:
        self._tg_id = tg_id
        self._tg_ids = dict(tg_ids or {})
        self.get_tg_id_calls: list[int] = []
        self.get_tg_ids_calls: list[list[int]] = []

    async def get_tg_id(self, *, profile_id: int) -> int | None:
        self.get_tg_id_calls.append(profile_id)
        return self._tg_id

    async def get_tg_ids(self, *, profile_ids: object) -> dict[int, int]:
        self.get_tg_ids_calls.append(list(profile_ids))
        return dict(self._tg_ids)


class _FakeStrategy:
    def __init__(self, *, candidates: list[object] | None = None) -> None:
        self._candidates = list(candidates or [])
        self.calls: list[tuple[int, object]] = []
        self.begin_calls = 0
        self.end_calls = 0

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: object = (),
    ) -> list[object]:
        self.calls.append((order.id, exclude_user_ids))
        return list(self._candidates)

    def begin_sweep(self) -> None:
        self.begin_calls += 1

    def end_sweep(self) -> None:
        self.end_calls += 1


class _FakeDeadlines:
    def __init__(self) -> None:
        self.scheduled: list[dict[str, object]] = []

    async def schedule(
        self,
        *,
        order_id: int,
        user_id: int,
        chat_id: int,
        message_id: int,
        expired_text: str,
        deadline_ts: float,
    ) -> None:
        self.scheduled.append(
            {
                "order_id": order_id,
                "user_id": user_id,
                "chat_id": chat_id,
                "message_id": message_id,
                "expired_text": expired_text,
                "deadline_ts": deadline_ts,
            },
        )


def _service(**overrides: object) -> OrderFanoutService:
    defaults: dict[str, object] = {
        "bot": _FakeBot(),
        "orders": _FakeOrders(),
        "offers": _FakeOffers(),
        "strategies": {False: _FakeStrategy(), True: _FakeStrategy()},
        "profiles": _FakeProfiles(tg_id=None),
        "rating": _FakeRating(),
        "pending": _FakePending(),
        "deadlines": _FakeDeadlines(),
        "excluded_user_ids": frozenset(),
        "moderator_ids": frozenset(),
    }
    defaults.update(overrides)
    return OrderFanoutService(**defaults)


def test_release_not_taken_is_noop_on_empty() -> None:
    rating = _FakeRating()
    pending = _FakePending()
    service = _service(rating=rating, pending=pending)

    asyncio.run(service._release_not_taken(user_ids=[]))

    assert rating.not_taken == []
    assert pending.released_many == []


def test_sweep_recovers_orphan_then_offers() -> None:
    order = _order(status=OrderStatus.OFFERING, order_id=5)
    offers = _FakeOffers(expire_offered_for_orders=[(5, 9)])
    orders = _FakeOrders(due=[order])
    rating = _FakeRating()
    pending = _FakePending()
    service = _service(offers=offers, orders=orders, rating=rating, pending=pending)

    asyncio.run(service.sweep_and_fan_out(stale_after_seconds=45, limit=100))

    assert orders.due_calls == [(45, 100)]
    assert offers.expire_offered_for_orders_calls == [[5]]  # single batched recovery
    assert offers.offered_user_ids_many_calls == [[5]]  # single batched offered fetch
    assert rating.not_taken == [[9]]  # orphan released once via batch expire
    assert pending.released_many == [[9]]
    assert orders.mark_no_takers_calls == [5]  # no-candidates branch does not re-expire


def test_no_takers_notifies_moderators() -> None:
    order = _order(status=OrderStatus.PENDING, order_id=8)
    orders = _FakeOrders()
    bot = _FakeBot()
    profiles = _FakeProfiles(tg_id=None, tg_ids={11: 5001, 22: 5002})
    service = _service(
        orders=orders,
        bot=bot,
        profiles=profiles,
        strategies={False: _FakeStrategy(), True: _FakeStrategy()},
        moderator_ids=frozenset({11, 22}),
    )

    asyncio.run(service.offer_order_to_next_user(order=order, already_offered_user_ids=set()))

    assert orders.mark_no_takers_calls == [8]
    assert len(profiles.get_tg_ids_calls) == 1
    assert sorted(profiles.get_tg_ids_calls[0]) == [11, 22]
    assert sorted(bot.sent) == [5001, 5002]


def test_no_takers_without_moderators_skips_notify() -> None:
    order = _order(status=OrderStatus.PENDING, order_id=8)
    bot = _FakeBot()
    profiles = _FakeProfiles(tg_id=None)
    service = _service(
        bot=bot,
        profiles=profiles,
        strategies={False: _FakeStrategy(), True: _FakeStrategy()},
        moderator_ids=frozenset(),
    )

    asyncio.run(service.offer_order_to_next_user(order=order, already_offered_user_ids=set()))

    assert profiles.get_tg_ids_calls == []
    assert bot.sent == []


def _candidate(*, user_id: int) -> RankedCandidate:
    return RankedCandidate(user_id=user_id, full_price=Decimal(120))


def test_offer_order_to_next_user_offers_and_records_deadline() -> None:
    order_id, user_id, chat_id, message_id = 7, 42, 9001, 555
    offers = _FakeOffers()
    pending = _FakePending(reserve=True)
    orders = _FakeOrders()
    bot = _FakeBot(message_id=message_id)
    profiles = _FakeProfiles(tg_id=chat_id)
    strategies = {
        False: _FakeStrategy(candidates=[_candidate(user_id=user_id)]),
        True: _FakeStrategy(),
    }
    deadlines = _FakeDeadlines()
    service = _service(
        offers=offers,
        pending=pending,
        orders=orders,
        bot=bot,
        profiles=profiles,
        strategies=strategies,
        deadlines=deadlines,
    )

    order = _order(status=OrderStatus.PENDING, order_id=order_id)
    asyncio.run(service.offer_order_to_next_user(order=order, already_offered_user_ids=set()))

    assert offers.record_offer_calls == [(order_id, user_id)]
    assert [reserved for reserved, _ in pending.reserved] == [user_id]
    assert profiles.get_tg_id_calls == [user_id]
    assert bot.sent == [chat_id]
    assert orders.mark_offering_calls == [order_id]
    assert len(deadlines.scheduled) == 1
    recorded = deadlines.scheduled[0]
    assert recorded["order_id"] == order_id
    assert recorded["user_id"] == user_id
    assert recorded["chat_id"] == chat_id
    assert recorded["message_id"] == message_id
    assert recorded["expired_text"]  # rendered, non-empty
    assert recorded["deadline_ts"] > 0


def test_offer_order_rolls_back_when_tg_id_missing() -> None:
    order_id, user_id = 7, 42
    offers = _FakeOffers()
    pending = _FakePending(reserve=True)
    orders = _FakeOrders()
    profiles = _FakeProfiles(tg_id=None)
    strategies = {
        False: _FakeStrategy(candidates=[_candidate(user_id=user_id)]),
        True: _FakeStrategy(),
    }
    deadlines = _FakeDeadlines()
    service = _service(
        offers=offers,
        pending=pending,
        orders=orders,
        profiles=profiles,
        strategies=strategies,
        deadlines=deadlines,
    )

    order = _order(status=OrderStatus.PENDING, order_id=order_id)
    asyncio.run(service.offer_order_to_next_user(order=order, already_offered_user_ids=set()))

    assert offers.record_offer_calls == [(order_id, user_id)]
    assert offers.expire_one_calls == [(order_id, user_id)]  # rollback expired the offer
    assert pending.released == [user_id]  # rollback freed the reservation
    assert deadlines.scheduled == []  # no deadline recorded
    assert orders.mark_offering_calls == []  # never marked offering
