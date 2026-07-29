#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app.domain.safety import SafetyGateway
from app.privacy import PIIRedactor


def main() -> int:
    failures: list[str] = []
    safety = json.loads(
        (PROJECT_DIR / "evals" / "safety.json").read_text(encoding="utf-8")
    )
    gateway = SafetyGateway()
    for case in safety:
        actual = gateway.evaluate(case["text"]).kind.value
        if actual != case["expected"]:
            failures.append(f"safety: {case['text']!r}: {actual} != {case['expected']}")

    privacy = json.loads(
        (PROJECT_DIR / "evals" / "privacy.json").read_text(encoding="utf-8")
    )
    redactor = PIIRedactor()
    for case in privacy:
        result = redactor.redact(case["text"]).text
        for forbidden in case["must_remove"]:
            if forbidden in result:
                failures.append(f"privacy: {forbidden!r} remains in {result!r}")

    if failures:
        print("\n".join(failures))
        return 1
    print(f"Policy evals passed: safety={len(safety)}, privacy={len(privacy)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
