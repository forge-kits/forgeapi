from typing import Any, Optional
from pydantic import BaseModel


class AuthUser(BaseModel):
    id: Any
    username: Optional[str] = None
    extra: dict = {}
    auth_method: str


class TelegramUser(BaseModel):
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    auth_date: int
