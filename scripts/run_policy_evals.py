#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.domain.models import SourceRef
from app.domain.safety import ResponseGuard, SafetyGateway
from app.privacy import PIIRedactor


def main() -> int:
    failures: list[str] = []
    safety = json.loads(
        (PROJECT_DIR / "evals" / "safety.json").read_text(encoding="utf-8")
    )
    gateway = SafetyGateway()
    redactor = PIIRedactor()
    for case in safety:
        pii = redactor.redact(case["text"]).categories
        actual = gateway.evaluate(case["text"], pii).kind.value
        if actual != case["expected"]:
            failures.append(f"safety: {case['text']!r}: {actual} != {case['expected']}")

    privacy = json.loads(
        (PROJECT_DIR / "evals" / "privacy.json").read_text(encoding="utf-8")
    )
    for case in privacy:
        result = redactor.redact(case["text"]).text
        for forbidden in case["must_remove"]:
            if forbidden in result:
                failures.append(f"privacy: {forbidden!r} remains in {result!r}")

    output_cases = json.loads(
        (PROJECT_DIR / "evals" / "output_guardrails.json").read_text(
            encoding="utf-8"
        )
    )
    output_guard = ResponseGuard()
    for index, case in enumerate(output_cases):
        sources = [
            SourceRef(
                id=f"eval-{index}-{source_index}",
                title="Eval source",
                url=case.get("source_url", "https://vodc.ru/"),
                excerpt=excerpt,
            )
            for source_index, excerpt in enumerate(case["sources"])
        ]
        actual = output_guard.evaluate(case["text"], sources).kind.value
        if actual != case["expected"]:
            failures.append(
                f"output: {case['text']!r}: {actual} != {case['expected']}"
            )

    if failures:
        print("\n".join(failures))
        return 1
    print(
        "Policy evals passed: "
        f"safety={len(safety)}, privacy={len(privacy)}, "
        f"output={len(output_cases)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
