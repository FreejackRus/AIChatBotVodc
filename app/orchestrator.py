from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from .domain.funnel import quick_replies, transition
from .domain.intents import classify_intent, policy_for
from .domain.models import (
    CardAction,
    ChatSession,
    Doctor,
    EntityCard,
    FunnelState,
    InputType,
    Service,
    Slot,
)
from .domain.priorities import ServicePrioritizer
from .domain.safety import SafetyGateway, SafetyKind
from .ports import (
    EventStore,
    KnowledgePort,
    KnowledgeUnavailable,
    MedAngelPort,
    MedAngelUnavailable,
    ModelPort,
    ModelUnavailable,
    SessionStore,
)
from .privacy import PIIRedactor
from .security import ActionTokenSigner, InvalidActionToken

logger = logging.getLogger(__name__)


class MessageRejected(ValueError):
    pass


class DependencyUnavailable(RuntimeError):
    pass


class DialogOrchestrator:
    def __init__(
        self,
        sessions: SessionStore,
        events: EventStore,
        knowledge: KnowledgePort,
        model: ModelPort,
        medangel: MedAngelPort,
        signer: ActionTokenSigner,
        redactor: PIIRedactor,
        rag_top_k: int,
        prioritizer: ServicePrioritizer | None = None,
    ):
        self.sessions = sessions
        self.events = events
        self.knowledge = knowledge
        self.model = model
        self.medangel = medangel
        self.signer = signer
        self.redactor = redactor
        self.safety = SafetyGateway()
        self.rag_top_k = rag_top_k
        self.prioritizer = prioritizer or ServicePrioritizer()

    async def _persist_message(
        self, session: ChatSession, role: str, text: str
    ) -> None:
        redacted = self.redactor.redact(text)
        await self.events.record_message(
            session.id, role, redacted.text, redacted.categories
        )

    def _service_cards(
        self, session: ChatSession, services: list[Service]
    ) -> list[EntityCard]:
        return [
            EntityCard(
                type="service",
                id=service.id,
                title=service.title,
                subtitle=service.description,
                facts=tuple(
                    fact
                    for fact in (
                        f"Цена: {service.price}" if service.price else None,
                        "Данные актуальны по МИС",
                    )
                    if fact
                ),
                actions=(
                    CardAction(
                        type=InputType.SELECT_SERVICE,
                        label="Выбрать услугу",
                        token=self.signer.issue(
                            session.id,
                            InputType.SELECT_SERVICE.value,
                            service.id,
                        ),
                    ),
                ),
            )
            for service in services
        ]

    def _doctor_cards(
        self, session: ChatSession, doctors: list[Doctor]
    ) -> list[EntityCard]:
        return [
            EntityCard(
                type="doctor",
                id=doctor.id,
                title=doctor.title,
                subtitle=doctor.specialty,
                actions=(
                    CardAction(
                        type=InputType.SELECT_DOCTOR,
                        label="Выбрать врача",
                        token=self.signer.issue(
                            session.id,
                            InputType.SELECT_DOCTOR.value,
                            doctor.id,
                        ),
                    ),
                ),
            )
            for doctor in doctors
        ]

    def _slot_cards(self, session: ChatSession, slots: list[Slot]) -> list[EntityCard]:
        return [
            EntityCard(
                type="slot",
                id=slot.id,
                title=slot.starts_at,
                subtitle="Свободное время по данным МИС",
                actions=(
                    CardAction(
                        type=InputType.SELECT_SLOT,
                        label="Выбрать время",
                        token=self.signer.issue(
                            session.id,
                            InputType.SELECT_SLOT.value,
                            slot.id,
                        ),
                    ),
                ),
            )
            for slot in slots
        ]

    async def _apply_action(
        self, session: ChatSession, input_type: InputType, token: str
    ) -> tuple[str, list[EntityCard]]:
        try:
            payload = self.signer.verify(
                token, session_id=session.id, action=input_type.value
            )
        except InvalidActionToken as exc:
            raise MessageRejected(str(exc)) from exc

        try:
            if input_type is InputType.SELECT_SERVICE:
                service = await self.medangel.validate_service(payload.entity_id)
                if not service:
                    raise MessageRejected("Услуга больше недоступна")
                session.selection.service_id = service.id
                session.selection.doctor_id = None
                session.selection.slot_id = None
                doctors = await self.medangel.doctors(
                    service.id, session.selection.branch_id
                )
                cards = self._doctor_cards(session, doctors)
                if not cards:
                    slots = await self.medangel.slots(
                        service.id, branch_id=session.selection.branch_id
                    )
                    cards = self._slot_cards(session, slots)
                return f"Выбрана услуга «{service.title}».", cards

            service_id = session.selection.service_id
            if not service_id:
                raise MessageRejected("Сначала выберите услугу")

            if input_type is InputType.SELECT_DOCTOR:
                doctor = await self.medangel.validate_doctor(
                    payload.entity_id, service_id
                )
                if not doctor:
                    raise MessageRejected("Врач больше недоступен для этой услуги")
                session.selection.doctor_id = doctor.id
                session.selection.branch_id = (
                    doctor.branch_id or session.selection.branch_id
                )
                session.selection.slot_id = None
                slots = await self.medangel.slots(
                    service_id, doctor.id, session.selection.branch_id
                )
                return (
                    f"Выбран врач {doctor.title}. Выберите свободное время.",
                    self._slot_cards(session, slots),
                )

            if input_type is InputType.SELECT_SLOT:
                slot = await self.medangel.validate_slot(payload.entity_id, service_id)
                if not slot:
                    raise MessageRejected(
                        "Слот уже недоступен. Обновите список времени."
                    )
                if (
                    session.selection.doctor_id
                    and slot.doctor_id != session.selection.doctor_id
                ):
                    raise MessageRejected("Слот относится к другому врачу")
                session.selection.slot_id = slot.id
                session.selection.doctor_id = slot.doctor_id
                session.selection.branch_id = (
                    slot.branch_id or session.selection.branch_id
                )
                selected_message = (
                    "Время выбрано. Нажмите «Перейти к записи», "
                    "чтобы открыть штатную форму ВОККДЦ."
                )
                return selected_message, []
        except MedAngelUnavailable as exc:
            raise DependencyUnavailable("Расписание временно недоступно") from exc
        raise MessageRejected("Неподдерживаемое действие")

    async def stream(
        self,
        session: ChatSession,
        input_type: InputType,
        *,
        text: str | None = None,
        token: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        started_at = time.perf_counter()
        yield {"event": "status", "data": {"phase": "processing"}}

        if input_type is not InputType.TEXT:
            response_text, cards = await self._apply_action(
                session, input_type, token or ""
            )
            session.state = transition(session.state, input_type)
            session.add_message("assistant", response_text)
            await self._persist_message(session, "assistant", response_text)
            await self.sessions.save(session)
            await self.events.record_event(
                session.id,
                input_type.value,
                {"state": session.state.value},
            )
            yield {"event": "text_delta", "data": {"text": response_text}}
            if cards:
                yield {
                    "event": "cards",
                    "data": {"items": [card.public_dict() for card in cards]},
                }
            yield {
                "event": "state",
                "data": {
                    "value": session.state.value,
                    "quick_replies": quick_replies(session.state),
                },
            }
            yield {
                "event": "done",
                "data": {
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000)
                },
            }
            return

        user_text = (text or "").strip()
        decision = self.safety.evaluate(user_text)
        intent = classify_intent(user_text)
        intent_policy = policy_for(intent)
        session.add_message("user", user_text)
        await self._persist_message(session, "user", user_text)

        if decision.blocked:
            if decision.kind is SafetyKind.EMERGENCY:
                session.state = FunnelState.SAFE_STOP
            response_text = decision.response or ""
            session.add_message("assistant", response_text)
            await self._persist_message(session, "assistant", response_text)
            await self.sessions.save(session)
            await self.events.record_event(
                session.id,
                decision.kind.value,
                {"state": session.state.value},
            )
            yield {"event": "text_delta", "data": {"text": response_text}}
            yield {
                "event": "state",
                "data": {
                    "value": session.state.value,
                    "quick_replies": quick_replies(session.state),
                },
            }
            yield {
                "event": "done",
                "data": {
                    "elapsed_ms": round((time.perf_counter() - started_at) * 1000)
                },
            }
            return

        yield {"event": "status", "data": {"phase": "retrieval"}}
        sources = []
        services: list[Service] = []
        mis_available = True
        page_path = re.sub(
            r"[^a-zа-яё0-9/_-]+",
            " ",
            urlparse(session.page_context.url).path.lower(),
        ).replace("-", " ")
        retrieval_query = f"{user_text} {page_path}".strip()
        try:
            sources = await self.knowledge.search(retrieval_query, self.rag_top_k)
        except KnowledgeUnavailable:
            logger.warning("Knowledge retrieval unavailable", exc_info=True)
        if intent_policy.uses_mis:
            try:
                services = self.prioritizer.rank(
                    await self.medangel.search_services(user_text)
                )
            except MedAngelUnavailable:
                mis_available = False

        cards = self._service_cards(session, services)
        session.state = transition(
            session.state,
            input_type,
            has_services=bool(services),
            intent=intent,
        )
        if sources:
            yield {
                "event": "sources",
                "data": {"items": [source.public_dict() for source in sources]},
            }
        if cards:
            yield {
                "event": "cards",
                "data": {"items": [card.public_dict() for card in cards]},
            }
        if not mis_available:
            yield {
                "event": "error",
                "data": {
                    "code": "mis_unavailable",
                    "message": (
                        "Расписание и цены временно недоступны. "
                        "Можно продолжить поиск по официальным материалам."
                    ),
                    "retryable": True,
                },
            }

        response_parts: list[str] = []
        if intent_policy.uses_mis:
            if not mis_available:
                fallback = (
                    "Не удалось получить актуальные данные МИС. "
                    "Откройте штатный поиск и запись ВОККДЦ."
                )
            elif cards:
                fallback = (
                    "Нашёл актуальные варианты по данным МИС. "
                    "Выберите подходящую услугу в карточках."
                )
            else:
                fallback = (
                    "В согласованном каталоге не найдено подходящих услуг. "
                    "Уточните запрос или откройте штатный поиск ВОККДЦ."
                )
            response_parts.append(fallback)
            yield {"event": "text_delta", "data": {"text": fallback}}
        elif not sources:
            fallback = (
                "В утверждённых источниках недостаточно данных для ответа. "
                "Уточните запрос или откройте штатный поиск и запись ВОККДЦ."
            )
            response_parts.append(fallback)
            yield {"event": "text_delta", "data": {"text": fallback}}
        else:
            yield {"event": "status", "data": {"phase": "generation"}}
        try:
            if sources and not intent_policy.uses_mis:
                async for delta in self.model.stream(
                    prompt=user_text,
                    history=session.history()[:-1],
                    sources=sources,
                ):
                    response_parts.append(delta)
                    yield {"event": "text_delta", "data": {"text": delta}}
        except ModelUnavailable:
            logger.warning("Model inference unavailable", exc_info=True)
            fallback = (
                "Не удалось получить ответ модели. "
                "Используйте подтверждённые ссылки ниже или штатную запись ВОККДЦ."
            )
            response_parts.append(fallback)
            yield {"event": "text_delta", "data": {"text": fallback}}
            yield {
                "event": "error",
                "data": {
                    "code": "model_unavailable",
                    "message": "Генерация временно недоступна",
                    "retryable": True,
                },
            }

        response_text = "".join(response_parts).strip()
        session.add_message("assistant", response_text)
        await self._persist_message(session, "assistant", response_text)
        await self.sessions.save(session)
        await self.events.record_event(
            session.id,
            "message_completed",
            {
                "state": session.state.value,
                "source_count": len(sources),
                "service_count": len(services),
                "mis_available": mis_available,
                "intent": intent.value,
            },
        )
        yield {
            "event": "state",
            "data": {
                "value": session.state.value,
                "quick_replies": quick_replies(session.state),
            },
        }
        yield {
            "event": "done",
            "data": {"elapsed_ms": round((time.perf_counter() - started_at) * 1000)},
        }
