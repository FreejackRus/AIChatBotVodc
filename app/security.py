from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


class InvalidActionToken(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ActionPayload:
    session_id: str
    action: str
    entity_id: str
    expires_at: int


class ActionTokenSigner:
    def __init__(self, secret: str, ttl_seconds: int = 900):
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def _encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

    @staticmethod
    def _decode(data: str) -> bytes:
        return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

    def issue(self, session_id: str, action: str, entity_id: str) -> str:
        body = json.dumps(
            {
                "sid": session_id,
                "action": action,
                "entity_id": entity_id,
                "exp": int(time.time()) + self._ttl_seconds,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._secret, body, hashlib.sha256).digest()
        return f"{self._encode(body)}.{self._encode(signature)}"

    def verify(
        self, token: str, *, session_id: str, action: str | None = None
    ) -> ActionPayload:
        try:
            encoded_body, encoded_signature = token.split(".", 1)
            body = self._decode(encoded_body)
            signature = self._decode(encoded_signature)
            data: dict[str, Any] = json.loads(body)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise InvalidActionToken("Некорректный action token") from exc
        expected = hmac.new(self._secret, body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidActionToken("Подпись action token неверна")
        if data.get("sid") != session_id:
            raise InvalidActionToken("Action token относится к другой сессии")
        if action and data.get("action") != action:
            raise InvalidActionToken("Action token имеет неверный тип")
        if int(data.get("exp", 0)) < int(time.time()):
            raise InvalidActionToken("Action token истёк")
        return ActionPayload(
            session_id=data["sid"],
            action=data["action"],
            entity_id=data["entity_id"],
            expires_at=int(data["exp"]),
        )
