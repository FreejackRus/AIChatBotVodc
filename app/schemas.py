from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from .domain.models import InputType


class PageContextRequest(BaseModel):
    url: HttpUrl
    title: str = Field(default="", max_length=300)
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: str | None = Field(default=None, max_length=100)


class ClientContext(BaseModel):
    locale: Literal["ru"] = "ru"
    timezone: str = Field(default="Europe/Moscow", max_length=64)
    privacy_notice_version: str | None = Field(default=None, max_length=32)


class CreateSessionRequest(BaseModel):
    page_context: PageContextRequest
    client: ClientContext = Field(default_factory=ClientContext)


class SessionResponse(BaseModel):
    session_id: str
    expires_in: int
    state: str
    welcome: str
    quick_replies: list[str]


class MessageInput(BaseModel):
    type: InputType
    text: str | None = None
    token: str | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> MessageInput:
        if self.type is InputType.TEXT and not (self.text or "").strip():
            raise ValueError("Для text требуется непустое поле text")
        if self.type is InputType.TEXT and self.token is not None:
            raise ValueError("Для text поле token запрещено")
        if self.type is not InputType.TEXT and not self.token:
            raise ValueError("Для действия требуется подписанный token")
        if self.type is not InputType.TEXT and self.text is not None:
            raise ValueError("Для действия поле text запрещено")
        return self


class MessageRequest(BaseModel):
    input: MessageInput
    client_message_id: Annotated[str, Field(min_length=1, max_length=100)]
    page_context: PageContextRequest | None = None


AllowedEvent = Literal[
    "widget_opened",
    "proactive_invitation_shown",
    "quick_reply_clicked",
    "service_card_opened",
    "booking_redirect_clicked",
    "widget_error",
]


class ClientEventRequest(BaseModel):
    type: AllowedEvent
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def limit_properties(self) -> ClientEventRequest:
        if len(self.properties) > 20:
            raise ValueError("Слишком много свойств события")
        allowed = {
            "code",
            "state",
            "service_id",
            "doctor_id",
            "branch_id",
            "card_type",
            "duration_ms",
            "page_type",
        }
        if not set(self.properties) <= allowed:
            raise ValueError("Событие содержит неразрешённые свойства")
        if any(
            isinstance(value, str) and len(value) > 100
            for value in self.properties.values()
        ):
            raise ValueError("Строковое свойство события слишком длинное")
        return self


class BookingLinkRequest(BaseModel):
    slot_token: str = Field(min_length=20, max_length=4096)


class BookingLinkResponse(BaseModel):
    url: HttpUrl
    expires_in: int = 900
