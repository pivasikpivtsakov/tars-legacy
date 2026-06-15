import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from common.models.orders import Order, OrderStatus
from common.services import order_fanout
from common.services.order_fanout import (
    FanoutContext,
    offer_order_to_next_user,
    sweep_and_fan_out,
)
from common.services.order_processing import RankedCandidate


def _order(*, status: OrderStatus, order_id: int = 1) -> Order:
    now = datetime.now(UTC)
    return Order(
        id=order_id,
        original_id=1,
        shop_access_key=None,
        status=status,
        status_reason=None,
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
    )


class _FakeOffers:
    def __init__(
        self,
        *,
        expire_one: int | None = None,
        expire_offered: list[int] | None = None,
        has_active: bool = False,
    ) -> None:
        self._expire_one = expire_one
        self._expire_offered = list(expire_offered or [])
        self._has_active = has_active
        self.expire_one_calls: list[tuple[int, int]] = []
        self.expire_offered_calls: list[int] = []
        self.has_active_offer_calls: list[tuple[int, int]] = []
        self.offered_user_ids_calls: list[int] = []
        self.record_offer_calls: list[tuple[int, int]] = []

    async def expire_one(self, *, order_id: int, user_id: int) -> int | None:
        self.expire_one_calls.append((order_id, user_id))
        return self._expire_one

    async def expire_offered(self, *, order_id: int) -> list[int]:
        self.expire_offered_calls.append(order_id)
        result = list(self._expire_offered)
        self._expire_offered = []  # rows already expired on subsequent calls
        return result

    async def has_active_offer(self, *, order_id: int, ttl_seconds: int) -> bool:
        self.has_active_offer_calls.append((order_id, ttl_seconds))
        return self._has_active

    async def offered_user_ids(self, *, order_id: int) -> set[int]:
        self.offered_user_ids_calls.append(order_id)
        return set()

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

    async def send_message(self, *, chat_id: int, text: str, reply_markup: object) -> object:
        self.sent.append(chat_id)
        assert text
        assert reply_markup is not None
        return SimpleNamespace(message_id=self._message_id)


class _FakeProfiles:
    def __init__(self, *, tg_id: int | None) -> None:
        self._tg_id = tg_id
        self.get_tg_id_calls: list[int] = []

    async def get_tg_id(self, *, profile_id: int) -> int | None:
        self.get_tg_id_calls.append(profile_id)
        return self._tg_id


class _FakeOrderManager:
    def __init__(self, *, candidates: list[object] | None = None) -> None:
        self._candidates = list(candidates or [])
        self.calls: list[object] = []

    async def select_candidates(
        self,
        *,
        order: Order,
        exclude_user_ids: object = (),
    ) -> list[object]:
        self.calls.append((order.id, exclude_user_ids))
        return list(self._candidates)

    def begin_sweep(self) -> None:
        pass

    def end_sweep(self) -> None:
        pass


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


def _ctx(**overrides: object) -> FanoutContext:
    defaults: dict[str, object] = {
        "bot": _FakeBot(),
        "orders": _FakeOrders(),
        "offers": _FakeOffers(),
        "profiles": None,
        "order_manager": _FakeOrderManager(),
        "rating": _FakeRating(),
        "pending": _FakePending(),
        "deadlines": _FakeDeadlines(),
        "excluded_user_ids": frozenset(),
    }
    defaults.update(overrides)
    return FanoutContext(**defaults)


def test_release_not_taken_is_noop_on_empty() -> None:
    rating = _FakeRating()
    pending = _FakePending()
    ctx = _ctx(rating=rating, pending=pending)

    asyncio.run(order_fanout._release_not_taken(ctx=ctx, user_ids=[]))

    assert rating.not_taken == []
    assert pending.released_many == []


def test_sweep_recovers_orphan_then_offers() -> None:
    order = _order(status=OrderStatus.OFFERING, order_id=5)
    offers = _FakeOffers(expire_offered=[9], has_active=False)
    orders = _FakeOrders(due=[order])
    rating = _FakeRating()
    pending = _FakePending()
    ctx = _ctx(offers=offers, orders=orders, rating=rating, pending=pending)

    asyncio.run(sweep_and_fan_out(ctx=ctx, stale_after_seconds=45, limit=100))

    assert orders.due_calls == [(45, 100)]
    assert offers.expire_offered_calls == [5, 5]  # recovery cleanup + no-candidates branch
    assert rating.not_taken == [[9]]  # orphan released once
    assert pending.released_many == [[9]]
    assert orders.mark_no_takers_calls == [5]


def _candidate(*, user_id: int) -> RankedCandidate:
    return RankedCandidate(
        user_id=user_id,
        full_price=120,
        speed_seconds=10,
        refusal_rate=0.0,
        complete=0,
    )


def test_offer_order_to_next_user_offers_and_records_deadline() -> None:
    order_id, user_id, chat_id, message_id = 7, 42, 9001, 555
    offers = _FakeOffers(has_active=False)
    pending = _FakePending(reserve=True)
    orders = _FakeOrders()
    bot = _FakeBot(message_id=message_id)
    profiles = _FakeProfiles(tg_id=chat_id)
    order_manager = _FakeOrderManager(candidates=[_candidate(user_id=user_id)])
    deadlines = _FakeDeadlines()
    ctx = _ctx(
        offers=offers,
        pending=pending,
        orders=orders,
        bot=bot,
        profiles=profiles,
        order_manager=order_manager,
        deadlines=deadlines,
    )

    order = _order(status=OrderStatus.PENDING, order_id=order_id)
    asyncio.run(offer_order_to_next_user(ctx=ctx, order=order))

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
    offers = _FakeOffers(has_active=False)
    pending = _FakePending(reserve=True)
    orders = _FakeOrders()
    profiles = _FakeProfiles(tg_id=None)
    order_manager = _FakeOrderManager(candidates=[_candidate(user_id=user_id)])
    deadlines = _FakeDeadlines()
    ctx = _ctx(
        offers=offers,
        pending=pending,
        orders=orders,
        profiles=profiles,
        order_manager=order_manager,
        deadlines=deadlines,
    )

    order = _order(status=OrderStatus.PENDING, order_id=order_id)
    asyncio.run(offer_order_to_next_user(ctx=ctx, order=order))

    assert offers.record_offer_calls == [(order_id, user_id)]
    assert offers.expire_one_calls == [(order_id, user_id)]  # rollback expired the offer
    assert pending.released == [user_id]  # rollback freed the reservation
    assert deadlines.scheduled == []  # no deadline recorded
    assert orders.mark_offering_calls == []  # never marked offering
