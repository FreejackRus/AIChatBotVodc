#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def validate_cases(
    cases: Any,
    minimum: int = 100,
    maximum: int = 200,
) -> list[str]:
    if not isinstance(cases, list):
        return ["gold set must be a JSON array"]
    failures = []
    if not minimum <= len(cases) <= maximum:
        failures.append(
            f"Gold set must contain {minimum}–{maximum} cases; "
            f"found {len(cases)}"
        )
    seen = set()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            failures.append(f"case {index}: object required")
            continue
        query = str(case.get("query", "")).strip()
        urls = case.get("expected_urls")
        if not query or not isinstance(urls, list) or not urls:
            failures.append(f"case {index}: query/expected_urls required")
            continue
        if query.casefold() in seen:
            failures.append(f"case {index}: duplicate query")
        seen.add(query.casefold())
        for url in urls:
            parsed = urlparse(str(url))
            if (
                parsed.scheme != "https"
                or parsed.hostname not in {"vodc.ru", "www.vodc.ru"}
                or parsed.query
                or parsed.fragment
            ):
                failures.append(f"case {index}: untrusted URL {url}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--minimum", type=int, default=100)
    parser.add_argument("--maximum", type=int, default=200)
    args = parser.parse_args()

    cases = json.loads(args.path.read_text(encoding="utf-8"))
    failures = validate_cases(cases, args.minimum, args.maximum)
    if failures:
        print("\n".join(failures))
        return 1
    print(f"Retrieval gold set is valid: {len(cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
