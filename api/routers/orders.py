from typing import Annotated, Optional

from fastapi import Request, APIRouter, status, Depends, HTTPException

from api.dependencies import get_order_entity_service
from api.constants.user_roles import UserRoleEnum
from api.authorization import (
    AuthorizationEnum,
)
from api.authorization import Authorization
from api.services.order_entity import OrderEntityService
from api.schemas.order import OrderResponse, OrderCreate


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
        tuple[Optional[int], Optional[UserRoleEnum]],
        Depends(
            Authorization(
                auth_type=AuthorizationEnum.INTERNAL,
            )
        ),
    ],
    request: Request,
    create_data: OrderCreate,
    service: OrderEntityService = Depends(get_order_entity_service),
) -> Optional[OrderResponse]:
    try:
        return await service.create(data=create_data)
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while processin: {ex}"
        ) from ex


@router.delete(
    path="/clean",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="💀💀💀 Сервисная ручка для отмены всего связанного с order.",
)
async def clean_order(
    _: Annotated[
        tuple[Optional[int], Optional[UserRoleEnum]],
        Depends(
            Authorization(
                auth_type=AuthorizationEnum.INTERNAL,
            )
        ),
    ],
    order_id: Optional[int] = None,
    original_id: Optional[int] = None,
    service: OrderEntityService = Depends(get_order_entity_service),
) -> None:
    if (not order_id and not original_id) or (order_id and original_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Need order_id or original_id",
        )
    await service.clean_order(order_id=order_id, original_id=original_id)
