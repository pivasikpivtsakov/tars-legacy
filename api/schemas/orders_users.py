from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class OrderUser(BaseModel):
    id: int
    user_id: Optional[int] = None
    order_id: Optional[int] = None
    is_pending: bool
    is_rejected: bool
    is_finished: bool
    created_at: datetime
    assigned_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    is_w_codes: Optional[bool] = None


class OrderUserCreateDB(BaseModel):
    user_id: Optional[int] = None
    order_id: Optional[int] = None
    is_pending: Optional[bool] = True


class OrderUserUpdateDB(BaseModel):
    user_id: Optional[int] = None
    is_pending: Optional[bool] = None
    is_rejected: Optional[bool] = None
    is_finished: Optional[bool] = None
    assigned_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    is_w_codes: Optional[bool] = None
