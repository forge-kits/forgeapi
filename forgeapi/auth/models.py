from typing import Any, Optional, Union
from pydantic import BaseModel, Field


class AuthUser(BaseModel):
    id: Union[str, int]
    username: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
    auth_method: str


class TelegramUser(BaseModel):
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    language_code: Optional[str] = None
    auth_date: int
