from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RedactionResult:
    text: str
    categories: tuple[str, ...]


class PIIRedactor:
    """Local deterministic redaction before durable persistence."""

    _patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        (
            "email",
            re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-zА-Яа-я]{2,}\b"),
        ),
        (
            "phone",
            re.compile(r"(?<!\d)(?:\+7|8)[\s()-]*(?:\d[\s()-]*){10}(?!\d)"),
        ),
        (
            "snils",
            re.compile(r"\b\d{3}[- ]?\d{3}[- ]?\d{3}[- ]?\d{2}\b"),
        ),
        (
            "policy",
            re.compile(r"\b(?:полис(?:а)?\s*)?(?:\d[\s-]*){16}\b", re.IGNORECASE),
        ),
        (
            "passport",
            re.compile(r"\b(?:паспорт\s*)?\d{2}\s?\d{2}\s?\d{6}\b", re.IGNORECASE),
        ),
        (
            "birth_date",
            re.compile(
                r"\b(?:0?[1-9]|[12]\d|3[01])[./-]"
                r"(?:0?[1-9]|1[0-2])[./-](?:19|20)\d{2}\b"
            ),
        ),
    )
    _fio = re.compile(
        r"\b[А-ЯЁ][а-яё]{2,}\s+[А-ЯЁ][а-яё]{2,}"
        r"(?:\s+[А-ЯЁ][а-яё]{2,})?\b"
    )

    def redact(self, text: str) -> RedactionResult:
        categories: list[str] = []
        redacted = text
        for category, pattern in self._patterns:
            redacted, count = pattern.subn(f"[{category.upper()}]", redacted)
            if count:
                categories.append(category)
        redacted, fio_count = self._fio.subn("[ФИО]", redacted)
        if fio_count:
            categories.append("fio")
        return RedactionResult(redacted, tuple(sorted(set(categories))))
