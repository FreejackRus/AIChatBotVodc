from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class FunnelState(StrEnum):
    DISCOVERY = "discovery"
    NEED_CLARIFICATION = "need_clarification"
    SERVICE_SHORTLIST = "service_shortlist"
    SERVICE_SELECTED = "service_selected"
    DOCTOR_SELECTED = "doctor_selected"
    SLOT_SELECTED = "slot_selected"
    BOOKING_REDIRECT = "booking_redirect"
    SAFE_STOP = "safe_stop"


class InputType(StrEnum):
    TEXT = "text"
    SELECT_SERVICE = "select_service"
    SELECT_DOCTOR = "select_doctor"
    SELECT_BRANCH = "select_branch"
    SELECT_SLOT = "select_slot"


@dataclass(slots=True)
class PageContext:
    url: str
    title: str = ""
    entity_type: str | None = None
    entity_id: str | None = None


@dataclass(frozen=True, slots=True)
class RetrievalContext:
    """Untrusted page URL; adapters match it only to approved source URLs."""

    page_url: str


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str
    created_at: str = field(default_factory=utcnow_iso)


@dataclass(slots=True)
class Selection:
    service_id: str | None = None
    doctor_id: str | None = None
    branch_id: str | None = None
    slot_id: str | None = None


@dataclass(slots=True)
class ChatSession:
    id: str
    page_context: PageContext
    state: FunnelState = FunnelState.DISCOVERY
    messages: list[ChatMessage] = field(default_factory=list)
    processed_client_message_ids: list[str] = field(default_factory=list)
    selection: Selection = field(default_factory=Selection)
    created_at: str = field(default_factory=utcnow_iso)
    updated_at: str = field(default_factory=utcnow_iso)

    def add_message(self, role: str, content: str) -> None:
        self.messages.append(ChatMessage(role=role, content=content))
        self.messages = self.messages[-20:]
        self.updated_at = utcnow_iso()

    def update_page_context(self, page_context: PageContext) -> None:
        self.page_context = page_context
        self.updated_at = utcnow_iso()

    def history(self) -> list[dict[str, str]]:
        return [
            {"role": message.role, "content": message.content}
            for message in self.messages[-10:]
        ]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["state"] = self.state.value
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatSession:
        return cls(
            id=str(data["id"]),
            page_context=PageContext(**data["page_context"]),
            state=FunnelState(data.get("state", FunnelState.DISCOVERY)),
            messages=[ChatMessage(**message) for message in data.get("messages", [])],
            processed_client_message_ids=list(
                data.get("processed_client_message_ids", [])
            )[-100:],
            selection=Selection(**data.get("selection", {})),
            created_at=data.get("created_at", utcnow_iso()),
            updated_at=data.get("updated_at", utcnow_iso()),
        )


@dataclass(frozen=True, slots=True)
class SourceRef:
    id: str
    title: str
    url: str
    excerpt: str
    reviewed_at: str | None = None
    score: float | None = None

    def public_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True, slots=True)
class Service:
    id: str
    title: str
    description: str = ""
    price: str | None = None
    branch_id: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class Doctor:
    id: str
    title: str
    specialty: str = ""
    branch_id: str | None = None
    service_id: str | None = None


@dataclass(frozen=True, slots=True)
class Slot:
    id: str
    starts_at: str
    doctor_id: str
    service_id: str
    branch_id: str | None = None


@dataclass(frozen=True, slots=True)
class CardAction:
    type: InputType
    label: str
    token: str


@dataclass(frozen=True, slots=True)
class EntityCard:
    type: str
    id: str
    title: str
    subtitle: str = ""
    facts: tuple[str, ...] = ()
    actions: tuple[CardAction, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "facts": list(self.facts),
            "actions": [
                {
                    "type": action.type.value,
                    "label": action.label,
                    "token": action.token,
                }
                for action in self.actions
            ],
        }
