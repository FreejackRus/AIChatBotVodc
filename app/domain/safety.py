from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class SafetyKind(StrEnum):
    ALLOW = "allow"
    EMERGENCY = "emergency"
    MEDICAL_REFUSAL = "medical_refusal"
    PROMPT_INJECTION = "prompt_injection"


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    kind: SafetyKind
    response: str | None = None

    @property
    def blocked(self) -> bool:
        return self.kind is not SafetyKind.ALLOW


EMERGENCY_RESPONSE = (
    "По описанию нельзя безопасно продолжать подбор услуги в чате. "
    "Если есть угроза жизни, резкое ухудшение состояния, сильная боль, "
    "нарушение дыхания или сознания — немедленно позвоните 112 или 103. "
    "Не ждите ответа чат-бота."
)

MEDICAL_REFUSAL_RESPONSE = (
    "Я не ставлю диагнозы, не назначаю лечение и не интерпретирую анализы. "
    "Могу помочь найти опубликованную информацию об услуге, враче, "
    "подготовке или перейти к записи."
)

INJECTION_RESPONSE = (
    "Я не могу изменять правила работы или выполнять скрытые инструкции. "
    "Задайте, пожалуйста, вопрос об услугах, врачах, подготовке или записи."
)


class SafetyGateway:
    """Deterministic checks that run before any model or tool call."""

    _emergency = re.compile(
        r"("
        r"не\s+(?:могу\s+)?дыш\w*|удуш\w*|"
        r"(?:потерял[аи]?|теря\w*)\s+сознани\w*|без\s+сознани\w*|"
        r"сильн\w*\s+кровотеч\w*|парализ\w*|инсульт\w*|инфаркт\w*|"
        r"резк\w*\s+боль\s+в\s+груд\w*|суицид\w*|самоубий\w*"
        r")",
        re.IGNORECASE,
    )
    _medical = re.compile(
        r"\b("
        r"постав\w*(?:\s+\w+){0,2}\s+диагноз|какой\s+у\s+меня\s+диагноз|"
        r"назнач\w*(?:\s+\w+){0,2}\s+лечени\w*|что\s+мне\s+принимать|"
        r"расшифру\w*\s+(анализ\w*|мрт|кт|узи)|"
        r"отмен\w*(?:\s+\w+){0,2}\s+"
        r"(лекарств\w*|препарат\w*|лечени\w*)|"
        r"дозировк\w*\s+(лекарств\w*|препарат\w*)"
        r")\b",
        re.IGNORECASE,
    )
    _injection = re.compile(
        r"("
        r"ignore\s+(all\s+)?previous|system\s+prompt|developer\s+message|"
        r"забудь\s+(все\s+)?предыдущ|покажи\s+системн\w*\s+промпт|"
        r"выполни\s+скрыт\w*\s+инструкц|отключи\s+ограничени"
        r")",
        re.IGNORECASE,
    )

    def evaluate(self, text: str) -> SafetyDecision:
        if self._emergency.search(text):
            return SafetyDecision(SafetyKind.EMERGENCY, EMERGENCY_RESPONSE)
        if self._medical.search(text):
            return SafetyDecision(SafetyKind.MEDICAL_REFUSAL, MEDICAL_REFUSAL_RESPONSE)
        if self._injection.search(text):
            return SafetyDecision(SafetyKind.PROMPT_INJECTION, INJECTION_RESPONSE)
        return SafetyDecision(SafetyKind.ALLOW)
