from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .models import Service


class ServicePrioritizer:
    """Ranks only already relevant MIS results; never injects a service."""

    def __init__(
        self,
        weights: dict[str, int] | None = None,
        allowed_service_ids: frozenset[str] | None = None,
    ):
        self.weights = weights or {}
        self.allowed_service_ids = allowed_service_ids

    @classmethod
    def from_file(cls, path: Path) -> ServicePrioritizer:
        if not path.exists():
            return cls()
        payload = json.loads(path.read_text(encoding="utf-8"))
        now = datetime.now(timezone.utc)
        weights: dict[str, int] = {}
        for rule in payload.get("rules", []):
            starts_at = rule.get("starts_at")
            ends_at = rule.get("ends_at")
            if starts_at and datetime.fromisoformat(starts_at) > now:
                continue
            if ends_at and datetime.fromisoformat(ends_at) < now:
                continue
            weights[str(rule["service_id"])] = int(rule.get("weight", 0))
        allowed_service_ids = frozenset(
            str(service_id)
            for service_id in payload.get("allowed_service_ids", [])
            if str(service_id).strip()
        )
        return cls(weights, allowed_service_ids)

    def rank(self, services: list[Service]) -> list[Service]:
        if self.allowed_service_ids is not None:
            services = [
                service
                for service in services
                if service.id in self.allowed_service_ids
            ]
        return sorted(
            services,
            key=lambda service: self.weights.get(service.id, 0),
            reverse=True,
        )
