from datetime import datetime

from pydantic import BaseModel


class OrderUser(BaseModel):
    id: int
    user_id: int | None = None
    order_id: int | None = None
    is_pending: bool
    is_rejected: bool
    is_finished: bool
    created_at: datetime
    assigned_at: datetime | None = None
    finished_at: datetime | None = None
    is_w_codes: bool | None = None


class OrderUserCreateDB(BaseModel):
    user_id: int | None = None
    order_id: int | None = None
    is_pending: bool | None = True


class OrderUserUpdateDB(BaseModel):
    user_id: int | None = None
    is_pending: bool | None = None
    is_rejected: bool | None = None
    is_finished: bool | None = None
    assigned_at: datetime | None = None
    finished_at: datetime | None = None
    is_w_codes: bool | None = None
