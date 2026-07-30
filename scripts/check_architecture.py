#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            result.add(f"{prefix}{node.module or ''}")
    return result


def check() -> list[str]:
    failures: list[str] = []
    for path in sorted((PROJECT_ROOT / "app" / "domain").glob("*.py")):
        for imported in imports(path):
            root = imported.split(".", 1)[0]
            invalid_relative = imported.startswith("..")
            invalid_absolute = (
                not imported.startswith(".")
                and root not in sys.stdlib_module_names
            )
            if invalid_relative or invalid_absolute:
                failures.append(
                    f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
                )

    forbidden_dependencies = {
        PROJECT_ROOT / "app" / "ports.py": (".adapters", "app.adapters"),
        PROJECT_ROOT / "app" / "orchestrator.py": (".adapters", "app.adapters"),
        PROJECT_ROOT / "app" / "main.py": (".adapters", "app.adapters"),
    }
    for path, prefixes in forbidden_dependencies.items():
        for imported in imports(path):
            if imported.startswith(prefixes):
                failures.append(
                    f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
                )
            if path.name == "orchestrator.py" and imported.split(".", 1)[0] in {
                "asyncpg",
                "httpx",
                "redis",
                "requests",
            }:
                failures.append(
                    f"{path.relative_to(PROJECT_ROOT)} imports {imported}"
                )
    return failures


def main() -> int:
    failures = check()
    if failures:
        print("\n".join(failures))
        return 1
    print("Architecture boundaries are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
