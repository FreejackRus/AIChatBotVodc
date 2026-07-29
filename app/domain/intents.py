from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Intent(StrEnum):
    SERVICE_SEARCH = "service_search"
    DOCTOR_SEARCH = "doctor_search"
    PREPARATION = "preparation"
    PRICE = "price"
    AVAILABILITY = "availability"
    BOOKING = "booking"
    ORGANIZATIONAL_INFO = "organizational_info"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class IntentPolicy:
    uses_knowledge: bool
    uses_mis: bool
    advances_funnel: bool


INTENT_POLICIES: dict[Intent, IntentPolicy] = {
    Intent.SERVICE_SEARCH: IntentPolicy(True, True, True),
    Intent.DOCTOR_SEARCH: IntentPolicy(True, True, True),
    Intent.PREPARATION: IntentPolicy(True, False, False),
    Intent.PRICE: IntentPolicy(True, True, True),
    Intent.AVAILABILITY: IntentPolicy(True, True, True),
    Intent.BOOKING: IntentPolicy(True, True, True),
    Intent.ORGANIZATIONAL_INFO: IntentPolicy(True, False, False),
    Intent.UNKNOWN: IntentPolicy(True, False, False),
}


_RULES: tuple[tuple[Intent, re.Pattern[str]], ...] = (
    (
        Intent.BOOKING,
        re.compile(r"\b(записа(?:ться|т|н)|запись|при[её]м)\b", re.IGNORECASE),
    ),
    (
        Intent.AVAILABILITY,
        re.compile(
            r"\b(свободн\w*|слот\w*|расписан\w*|врем(?:я|ени)|дат[ауые])\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.PRICE,
        re.compile(
            r"\b(цен[аыуе]?|стоимост\w*|сколько стоит|платн\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.PREPARATION,
        re.compile(
            r"\b(подготов\w*|натощак|перед исследован\w*|можно ли есть)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.DOCTOR_SEARCH,
        re.compile(
            r"\b(врач\w*|доктор\w*|специалист\w*|кардиолог\w*|"
            r"невролог\w*|эндокринолог\w*|рентгенолог\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.ORGANIZATIONAL_INFO,
        re.compile(
            r"\b(адрес\w*|телефон\w*|контакт\w*|как добраться|"
            r"режим работ\w*|часы работ\w*|где наход\w*|филиал\w*)\b",
            re.IGNORECASE,
        ),
    ),
    (
        Intent.SERVICE_SEARCH,
        re.compile(
            r"\b(услуг\w*|исследован\w*|диагностик\w*|анализ\w*|"
            r"консультац\w*|мрт|кт|узи|рентген\w*|маммограф\w*|"
            r"эндоскоп\w*|флюорограф\w*)\b",
            re.IGNORECASE,
        ),
    ),
)


def classify_intent(text: str) -> Intent:
    normalized = " ".join(text.split())
    for intent, pattern in _RULES:
        if pattern.search(normalized):
            return intent
    return Intent.UNKNOWN


def policy_for(intent: Intent) -> IntentPolicy:
    return INTENT_POLICIES[intent]
