from __future__ import annotations

from .intents import Intent, policy_for
from .models import FunnelState, InputType

QUICK_REPLIES: dict[FunnelState, tuple[str, ...]] = {
    FunnelState.DISCOVERY: (
        "Найти услугу",
        "Найти врача",
        "Как подготовиться?",
    ),
    FunnelState.NEED_CLARIFICATION: (
        "Подобрать услугу",
        "Показать врачей",
        "Уточнить подготовку",
    ),
    FunnelState.SERVICE_SHORTLIST: (),
    FunnelState.SERVICE_SELECTED: (
        "Выбрать врача",
        "Показать свободное время",
    ),
    FunnelState.DOCTOR_SELECTED: ("Показать свободное время",),
    FunnelState.SLOT_SELECTED: ("Перейти к записи",),
    FunnelState.BOOKING_REDIRECT: (),
    FunnelState.SAFE_STOP: ("Найти контакты центра",),
}


def transition(
    current: FunnelState,
    input_type: InputType,
    *,
    has_services: bool = False,
    intent: Intent | None = None,
) -> FunnelState:
    if input_type is InputType.SELECT_SERVICE:
        return FunnelState.SERVICE_SELECTED
    if input_type is InputType.SELECT_DOCTOR:
        return FunnelState.DOCTOR_SELECTED
    if input_type is InputType.SELECT_SLOT:
        return FunnelState.SLOT_SELECTED
    if input_type is InputType.SELECT_BRANCH:
        return current
    if intent is not None and not policy_for(intent).advances_funnel:
        return current
    if has_services:
        return FunnelState.SERVICE_SHORTLIST
    if current is FunnelState.DISCOVERY:
        return FunnelState.NEED_CLARIFICATION
    return current


def quick_replies(state: FunnelState) -> list[str]:
    return list(QUICK_REPLIES[state])
