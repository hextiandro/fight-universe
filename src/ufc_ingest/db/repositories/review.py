"""Cola de revisión y registro de cambios. La revisión es un estado del dato, no algo aparte."""

import json
from typing import Any

import psycopg


def enqueue(cur: psycopg.Cursor, candidate: dict[str, Any], reason: str, confidence: int) -> int | None:
    """Encola un candidato. Si ya hay uno idéntico pendiente, no lo duplica."""
    cur.execute(
        """
        select id from review_queue
         where state = 'pending' and candidate->>'key' = %s
        """,
        (candidate.get("key"),),
    )
    if cur.fetchone():
        return None
    cur.execute(
        """
        insert into review_queue (candidate, reason, confidence) values (%s, %s, %s)
        returning id
        """,
        (json.dumps(candidate, ensure_ascii=False, default=str), reason, confidence),
    )
    return cur.fetchone()["id"]


def pending(cur: psycopg.Cursor, limit: int = 50) -> list[dict[str, Any]]:
    cur.execute(
        """
        select id, candidate, reason, confidence, created_at
          from review_queue where state = 'pending'
         order by (candidate->>'kind') desc, created_at limit %s
        """,
        (limit,),
    )
    return cur.fetchall()


def decide(cur: psycopg.Cursor, item_id: int, state: str, actor: str) -> None:
    cur.execute(
        "update review_queue set state = %s, decided_by = %s, decided_at = now() where id = %s",
        (state, actor, item_id),
    )


def log(
    cur: psycopg.Cursor, actor: str, action: str, entity: str, after: dict[str, Any] | None = None
) -> None:
    cur.execute(
        "insert into change_log (actor, action, entity, after) values (%s, %s, %s, %s)",
        (actor, action, entity, json.dumps(after, ensure_ascii=False, default=str) if after else None),
    )


def add_external_id(cur: psycopg.Cursor, fighter_id: str, system: str, value: str) -> None:
    cur.execute(
        """
        insert into fighter_external_ids (fighter_id, system, value) values (%s, %s, %s)
        on conflict (system, value) do nothing
        """,
        (fighter_id, system, value),
    )


def event_id_by_slug(cur: psycopg.Cursor, slug: str) -> str | None:
    cur.execute("select id from events where slug = %s", (slug,))
    row = cur.fetchone()
    return row["id"] if row else None


def event_date(cur: psycopg.Cursor, event_id: str) -> Any | None:
    cur.execute("select date from events where id = %s", (event_id,))
    row = cur.fetchone()
    return row["date"] if row else None


def fight_exists(cur: psycopg.Cursor, fight_id: str) -> bool:
    cur.execute("select 1 from fights where id = %s", (fight_id,))
    return cur.fetchone() is not None
