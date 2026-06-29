from common.services.order_timeouts import OrderTimeoutService

_services: dict[str, OrderTimeoutService] = {}


def set_job_services(*, order_timeouts: OrderTimeoutService) -> None:
    _services["order_timeouts"] = order_timeouts


def get_order_timeouts() -> OrderTimeoutService:
    service = _services.get("order_timeouts")
    if service is None:
        raise RuntimeError("order timeout service is not configured")
    return service
