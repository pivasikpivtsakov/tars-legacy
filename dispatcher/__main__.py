import asyncio
import contextlib
import logging

from redis.exceptions import RedisError

from common.bot import create_bot
from common.db import create_pool
from common.environment import (
    DISPATCH_BACKSTOP_SECONDS,
    DISPATCH_BATCH_LIMIT,
    MODERATOR_USER_IDS,
    OFFER_RECONCILE_GRACE_SECONDS,
    OFFER_TTL_SECONDS,
    TELEGRAM_BOT_TOKEN,
)
from common.logging_config import setup_logging
from common.redis import create_redis
from common.services.dispatch_signal import DispatchSignal
from common.services.order_fanout import FanoutContext, build_fanout_context, sweep_and_fan_out

logger = logging.getLogger(__name__)

_RECONNECT_DELAY_SECONDS = 1.0


async def _safe_sweep(*, ctx: FanoutContext, stale_after_seconds: int) -> None:
    try:
        await sweep_and_fan_out(
            ctx=ctx,
            stale_after_seconds=stale_after_seconds,
            limit=DISPATCH_BATCH_LIMIT,
        )
    except Exception:
        logger.exception("order dispatch sweep failed")


async def main() -> None:
    setup_logging()
    stale_after = OFFER_TTL_SECONDS + OFFER_RECONCILE_GRACE_SECONDS
    async with create_pool() as pool:
        redis = create_redis()
        bot = create_bot(token=TELEGRAM_BOT_TOKEN)
        signal = DispatchSignal(redis=redis)
        ctx = build_fanout_context(
            pool=pool,
            redis=redis,
            bot=bot,
            excluded_user_ids=MODERATOR_USER_IDS,
        )
        logger.info("starting dispatcher")
        try:
            while True:
                try:
                    async with signal.subscribe() as wakes:
                        # Sweep once on (re)connect to drain backlog before waiting.
                        await _safe_sweep(ctx=ctx, stale_after_seconds=stale_after)
                        while True:
                            await wakes.wait(timeout_seconds=DISPATCH_BACKSTOP_SECONDS)
                            await _safe_sweep(ctx=ctx, stale_after_seconds=stale_after)
                except RedisError:
                    logger.warning("dispatch wake channel dropped; reconnecting", exc_info=True)
                    await asyncio.sleep(_RECONNECT_DELAY_SECONDS)
        finally:
            await bot.session.close()
            await redis.aclose()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
