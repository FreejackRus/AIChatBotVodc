#!/usr/bin/env python3
"""Manual smoke test for the versioned SSE API."""

from __future__ import annotations

import argparse
import json
import uuid

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:5000")
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")

    with httpx.Client(timeout=90) as client:
        session_response = client.post(
            f"{base_url}/api/v1/sessions",
            json={
                "page_context": {
                    "url": f"{base_url}/",
                    "title": "Smoke test",
                }
            },
        )
        session_response.raise_for_status()
        session_id = session_response.json()["session_id"]

        with client.stream(
            "POST",
            f"{base_url}/api/v1/sessions/{session_id}/messages/stream",
            json={
                "input": {"type": "text", "text": "Что такое ВОККДЦ?"},
                "client_message_id": str(uuid.uuid4()),
            },
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            done = False
            for line in response.iter_lines():
                if line:
                    print(line)
                if line.startswith("event: done"):
                    done = True
            if not done:
                print(json.dumps({"error": "SSE stream ended without done event"}))
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
