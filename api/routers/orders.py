import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from api.authorization import (
    Authorization,
    AuthorizationEnum,
)
from api.constants.user_roles import UserRoleEnum
from api.dependencies import get_order_entity_service
from api.schemas.order import OrderCreate, OrderResponse
from api.services.order_entity import OrderEntityService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/orders",
    tags=["orders"],
)


@router.post(
    path="/create",
    status_code=status.HTTP_201_CREATED,
    summary="Добавление заказа для ручной активации.",
)
async def create_order(
    _: Annotated[
        tuple[int | None, UserRoleEnum | None],
        Depends(
            Authorization(
                auth_type=AuthorizationEnum.INTERNAL,
            )
        ),
    ],
    create_data: OrderCreate,
    service: Annotated[OrderEntityService, Depends(get_order_entity_service)],
) -> OrderResponse | None:
    try:
        return await service.create(data=create_data)
    except Exception as ex:
        logger.exception("Order creation failed for original_id=%s", create_data.id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while processing: {ex}",
        ) from ex


@router.delete(
    path="/clean",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="💀💀💀 Сервисная ручка для отмены всего связанного с order.",
)
async def clean_order(
    _: Annotated[
        tuple[int | None, UserRoleEnum | None],
        Depends(
            Authorization(
                auth_type=AuthorizationEnum.INTERNAL,
            )
        ),
    ],
    service: Annotated[OrderEntityService, Depends(get_order_entity_service)],
    order_id: int | None = None,
    original_id: int | None = None,
) -> None:
    if (not order_id and not original_id) or (order_id and original_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Need order_id or original_id",
        )
    await service.clean_order(order_id=order_id, original_id=original_id)
