from common.environment import OFFER_RECONCILE_GRACE_SECONDS, OFFER_TTL_SECONDS
from common.services.order_fanout import get_fanout_context, sweep_and_fan_out


async def dispatch_once() -> None:
    await sweep_and_fan_out(
        ctx=get_fanout_context(),
        stale_after_seconds=OFFER_TTL_SECONDS + OFFER_RECONCILE_GRACE_SECONDS,
    )


async def job__order_fanout() -> None:
    get_fanout_context().request_dispatch()
