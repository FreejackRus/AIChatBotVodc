#!/usr/bin/env python3
"""Record a human decision for a staged semantic source version."""

from __future__ import annotations

import argparse
import asyncio
import os
import uuid

import asyncpg


async def review(
    database_url: str,
    version_id: uuid.UUID,
    decision: str,
    reviewer: str,
    reviewer_role: str,
    reason: str,
) -> None:
    connection = await asyncpg.connect(database_url)
    try:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT v.review_status, v.quality_issues, c.risk_tier
                FROM source_versions v
                JOIN source_candidates c ON c.id = v.candidate_id
                WHERE v.id = $1
                FOR UPDATE
                """,
                version_id,
            )
            if row is None:
                raise ValueError("Версия источника не найдена")
            if decision == "approved" and row["review_status"] != "pending_review":
                raise ValueError(
                    "Утвердить можно только pending_review без quality issues"
                )
            if decision == "approved" and row["quality_issues"]:
                raise ValueError("Версия с quality issues не может быть утверждена")
            if (
                decision == "approved"
                and row["risk_tier"] == "medical"
                and reviewer_role != "medical_owner"
            ):
                raise ValueError(
                    "Медицинскую версию утверждает только medical_owner"
                )
            if row["review_status"] in {"approved", "rejected"}:
                raise ValueError("Для версии уже записано окончательное решение")
            await connection.execute(
                """
                INSERT INTO source_version_reviews
                    (version_id, decision, reviewer, reviewer_role, reason)
                VALUES ($1, $2, $3, $4, $5)
                """,
                version_id,
                decision,
                reviewer,
                reviewer_role,
                reason,
            )
            await connection.execute(
                """
                UPDATE source_versions
                SET review_status = $2
                WHERE id = $1
                """,
                version_id,
                decision,
            )
    finally:
        await connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("version_id", type=uuid.UUID)
    parser.add_argument("decision", choices=("approved", "rejected"))
    parser.add_argument("--reviewer", required=True)
    parser.add_argument(
        "--reviewer-role",
        required=True,
        choices=("content_owner", "medical_owner"),
    )
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL обязателен")
    reviewer = args.reviewer.strip()
    reason = args.reason.strip()
    if len(reviewer) < 3:
        raise SystemExit("--reviewer должен содержать имя ответственного")
    if len(reason) < 10:
        raise SystemExit("--reason должен содержать обоснование решения")
    asyncio.run(
        review(
            database_url,
            args.version_id,
            args.decision,
            reviewer,
            args.reviewer_role,
            reason,
        )
    )


if __name__ == "__main__":
    main()
