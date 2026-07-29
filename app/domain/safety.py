from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from .models import SourceRef


def normalize_security_text(text: str) -> str:
    """Canonicalize text before security matching, including invisible attacks."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = "".join(
        character
        for character in normalized
        if unicodedata.category(character) not in {"Cf", "Cc"}
        or character in "\n\t"
    )
    return " ".join(normalized.casefold().split())


class SafetyKind(StrEnum):
    ALLOW = "allow"
    EMERGENCY = "emergency"
    MEDICAL_REFUSAL = "medical_refusal"
    PROMPT_INJECTION = "prompt_injection"
    PII = "pii"


@dataclass(frozen=True, slots=True)
class SafetyDecision:
    kind: SafetyKind
    response: str | None = None

    @property
    def blocked(self) -> bool:
        return self.kind is not SafetyKind.ALLOW


class OutputSafetyKind(StrEnum):
    ALLOW = "allow"
    MEDICAL_CONTENT = "medical_content"
    DYNAMIC_DATA = "dynamic_data"
    PROMPT_DISCLOSURE = "prompt_disclosure"
    UNSUPPORTED_FACT = "unsupported_fact"


@dataclass(frozen=True, slots=True)
class OutputSafetyDecision:
    kind: OutputSafetyKind
    detail: str | None = None

    @property
    def blocked(self) -> bool:
        return self.kind is not OutputSafetyKind.ALLOW


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

PII_RESPONSE = (
    "Не отправляйте в чат ФИО, телефон, email, дату рождения, данные "
    "документов, полиса или другие медицинские идентификаторы. "
    "Введите их только в штатной форме записи ВОККДЦ."
)

UNSAFE_OUTPUT_RESPONSE = (
    "Не могу безопасно показать ответ модели. "
    "Используйте подтверждённые ссылки ниже или уточните информационный запрос."
)


_PROMPT_INJECTION = re.compile(
    r"("
    r"ignore\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|rules?)|"
    r"(?:reveal|show|print|repeat|extract)\s+(?:the\s+)?system\s+prompt|"
    r"system\s+prompt|developer\s+message|jailbreak|"
    r"forget\s+(?:all\s+)?(?:previous|prior)\s+(?:instructions?|rules?)|"
    r"забудь\s+(?:все\s+)?предыдущ\w*(?:\s+\w+){0,2}|"
    r"(?:покажи|раскрой|выведи|повтори)\s+(?:полный\s+)?"
    r"(?:системн\w*\s+промпт|скрыт\w*\s+инструкц\w*)|"
    r"выполни\s+скрыт\w*\s+инструкц\w*|"
    r"(?:отключи|обойди|игнорируй)\s+(?:все\s+)?"
    r"(?:ограничени\w*|правил\w*|инструкц\w*)"
    r")"
)
_BASE64_TOKEN = re.compile(
    r"(?<![a-z0-9+/=_-])[a-z0-9+/_-]{24,}={0,2}(?![a-z0-9+/=_-])",
    re.IGNORECASE,
)
_LATIN_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "с": "c",
        "е": "e",
        "і": "i",
        "к": "k",
        "м": "m",
        "о": "o",
        "р": "p",
        "т": "t",
        "х": "x",
        "у": "y",
    }
)


def contains_prompt_injection(text: str) -> bool:
    normalized = normalize_security_text(text)
    if _PROMPT_INJECTION.search(normalized):
        return True
    if _PROMPT_INJECTION.search(normalized.translate(_LATIN_CONFUSABLES)):
        return True
    for token in _BASE64_TOKEN.findall(unicodedata.normalize("NFKC", text)):
        if len(token) > 8192:
            continue
        try:
            decoded = base64.b64decode(
                token.replace("-", "+").replace("_", "/")
                + "=" * (-len(token) % 4),
                validate=True,
            ).decode("utf-8")
        except (ValueError, UnicodeDecodeError, binascii.Error):
            continue
        if _PROMPT_INJECTION.search(normalize_security_text(decoded)):
            return True
    return False


class SafetyGateway:
    """Deterministic checks that run before intent, retrieval, model and tools."""

    _emergency = re.compile(
        r"("
        r"не\s+(?:могу\s+)?дыш\w*|удуш\w*|задыха\w*|"
        r"(?:потерял\w*|теря\w*)\s+сознани\w*|без\s+сознани\w*|"
        r"сильн\w*\s+кровотеч\w*|не\s+останавлива\w*\s+кров\w*|"
        r"кров\w*\s+не\s+останавлива\w*|"
        r"парализ\w*|инсульт\w*|инфаркт\w*|"
        r"резк\w*\s+боль\s+в\s+груд\w*|"
        r"суицид\w*|самоубий\w*|хочу\s+умереть|покончить\s+с\s+собой"
        r")"
    )
    _medical = re.compile(
        r"\b("
        r"постав\w*(?:\s+\w+){0,2}\s+диагноз|какой\s+у\s+меня\s+диагноз|"
        r"определи\s+(?:мо[юё]\s+)?болезн\w*|"
        r"назнач\w*(?:\s+\w+){0,2}\s+лечени\w*|что\s+мне\s+принимать|"
        r"какие\s+(?:таблетк\w*|лекарств\w*|препарат\w*)\s+принимать|"
        r"расшифру\w*\s+(?:анализ\w*|мрт|кт|узи)|"
        r"интерпретир\w*\s+(?:анализ\w*|результат\w*)|"
        r"что\s+означа\w*\s+(?:мой|мои)\s+(?:анализ\w*|результат\w*)|"
        r"(?:как|чем)\s+лечить\s+\w+|"
        r"можно\s+ли\s+мне\s+(?:принимать|принять)\s+\w+|"
        r"оцени\s+(?:мои\s+)?симптом\w*|"
        r"что\s+делать[\s,;:-]+(?:если|при)\s+(?:у\s+меня\s+)?"
        r"(?:бол\w*|симптом\w*|температур\w*|давлени\w*)|"
        r"нормально\s+ли[, ]+(?:что|если)\s+(?:у\s+меня\s+)?"
        r"(?:бол\w*|температур\w*|давлени\w*)|"
        r"отмен\w*(?:\s+\w+){0,2}\s+"
        r"(?:лекарств\w*|препарат\w*|лечени\w*)|"
        r"дозировк\w*\s+(?:лекарств\w*|препарат\w*)"
        r")\b"
    )

    def evaluate(
        self, text: str, pii_categories: tuple[str, ...] = ()
    ) -> SafetyDecision:
        normalized = normalize_security_text(text)
        if self._emergency.search(normalized):
            return SafetyDecision(SafetyKind.EMERGENCY, EMERGENCY_RESPONSE)
        if self._medical.search(normalized):
            return SafetyDecision(SafetyKind.MEDICAL_REFUSAL, MEDICAL_REFUSAL_RESPONSE)
        if contains_prompt_injection(text):
            return SafetyDecision(SafetyKind.PROMPT_INJECTION, INJECTION_RESPONSE)
        if pii_categories:
            return SafetyDecision(SafetyKind.PII, PII_RESPONSE)
        return SafetyDecision(SafetyKind.ALLOW)


class ResponseGuard:
    """Fail-closed validation for model text before a fragment reaches SSE."""

    _medical = re.compile(
        r"("
        r"(?:у\s+вас|ваш\s+диагноз)[\s.,;:!?-]+"
        r"(?:диабет|рак|инфаркт|инсульт|"
        r"пневмони\w*|гипертони\w*|болезн\w*)|"
        r"(?:это|признак\w*\s+указыва\w*\s+на)[\s.,;:!?-]+"
        r"(?:диабет|рак|инфаркт|инсульт|пневмони\w*|гипертони\w*)|"
        r"(?:рекомендую|вам\s+(?:следует|нужно|необходимо))[\s.,;:!?-]+"
        r"(?:принимать|принять|начать|отменить|увеличить|уменьшить)|"
        r"(?:принимайте|примите|выпейте|отмените|начните)\s+"
        r"(?:лекарств\w*|препарат\w*|"
        r"таблетк\w*|\w+\s+\d+\s*(?:мг|мл))|"
        r"(?:анализ\w*|результат\w*)\s+(?:показыва\w*|означа\w*)|"
        r"дозировк\w*\s+(?:составля\w*|должн\w*|лекарств\w*|препарат\w*)"
        r")"
    )
    _dynamic = re.compile(
        r"("
        r"\b\d[\d\s.,]*\s*(?:₽|руб(?:ль|ля|лей)?\.?)(?!\w)|"
        r"(?:свободн\w*[\s.,;:!?-]+(?:слот\w*|врем\w*)|"
        r"(?:слот|запись)\s+(?:доступ\w*|свобод\w*))|"
        r"(?:врач|доктор)\s+[а-яё-]{2,}"
        r"(?:\s+[а-яё-]{2,}|\s+[а-яё]\.)?"
        r")"
    )
    _prompt_disclosure = re.compile(
        r"("
        r"(?:системн\w*|скрыт\w*)[\s.,;:!?-]+"
        r"(?:промпт|инструкц\w*)|"
        r"(?:system|developer)\s+(?:prompt|message)|"
        r"мои\s+внутренн\w*\s+правил\w*"
        r")"
    )
    _email = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-zа-яё]{2,}\b")
    _url = re.compile(r"https?://[^\s<>\"]+")
    _phone = re.compile(r"(?<!\d)(?:\+7|8)[\s()-]*(?:\d[\s()-]*){10}(?!\d)")
    _number = re.compile(r"(?<![\d\[])\d(?:[\d\s().:+/-]{0,24}\d)?(?![\d\]])")

    @staticmethod
    def _source_corpus(sources: list[SourceRef]) -> str:
        return normalize_security_text(
            "\n".join(
                f"{source.title}\n{source.url}\n{source.excerpt}"
                for source in sources
            )
        )

    @staticmethod
    def _digits(text: str) -> str:
        return "".join(character for character in text if character.isdigit())

    def evaluate(
        self, text: str, sources: list[SourceRef]
    ) -> OutputSafetyDecision:
        normalized = normalize_security_text(text)
        if not normalized:
            return OutputSafetyDecision(OutputSafetyKind.ALLOW)
        if self._prompt_disclosure.search(normalized):
            return OutputSafetyDecision(OutputSafetyKind.PROMPT_DISCLOSURE)
        if self._medical.search(normalized):
            return OutputSafetyDecision(OutputSafetyKind.MEDICAL_CONTENT)
        if self._dynamic.search(normalized):
            return OutputSafetyDecision(OutputSafetyKind.DYNAMIC_DATA)

        corpus = self._source_corpus(sources)
        corpus_digits = self._digits(corpus)
        for value in self._email.findall(normalized):
            if value not in corpus:
                return OutputSafetyDecision(
                    OutputSafetyKind.UNSUPPORTED_FACT, "email"
                )
        for value in self._url.findall(normalized):
            if value.rstrip(".,);") not in corpus:
                return OutputSafetyDecision(OutputSafetyKind.UNSUPPORTED_FACT, "url")
        for value in self._phone.findall(normalized):
            if self._digits(value) not in corpus_digits:
                return OutputSafetyDecision(
                    OutputSafetyKind.UNSUPPORTED_FACT, "phone"
                )
        for value in self._number.findall(normalized):
            digits = self._digits(value)
            if len(digits) >= 2 and digits not in corpus_digits:
                return OutputSafetyDecision(
                    OutputSafetyKind.UNSUPPORTED_FACT, "number"
                )
        return OutputSafetyDecision(OutputSafetyKind.ALLOW)
