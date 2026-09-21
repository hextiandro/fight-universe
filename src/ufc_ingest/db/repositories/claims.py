"""Procedencia: un claim por fuente, con su orden (la primera es la principal)."""

import json

import psycopg

from ...domain.models import Claim


def record(cur: psycopg.Cursor, claim: Claim, fallback_source: str) -> None:
    sources = claim.provenance.source_ids or [fallback_source]
    for rank, source_id in enumerate(sources):
        cur.execute(
            """
            insert into claims
              (subject_type, subject_id, field, value, source_id, source_rank,
               confidence, verified, note, valid_from)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (subject_type, subject_id, field, source_id, md5(value::text))
            do update set
              source_rank = excluded.source_rank, confidence = excluded.confidence,
              verified = excluded.verified, note = excluded.note,
              valid_from = excluded.valid_from
            """,
            (
                claim.subject_type,
                claim.subject_id,
                claim.field,
                json.dumps(claim.value, ensure_ascii=False, default=str),
                source_id,
                rank,
                90 if claim.provenance.verified else 50,
                claim.provenance.verified,
                claim.provenance.note,
                claim.valid_from,
            ),
        )


def winning_values(cur: psycopg.Cursor, subject_type: str) -> list[dict]:
    """Valor vigente de cada campo: gana lo verificado, luego la fuente de más confianza,
    y a igualdad lo más reciente. Es la regla de conflicto entre fuentes."""
    cur.execute(
        """
        select distinct on (c.subject_id, c.field)
               c.subject_id, c.field, c.value, c.source_id, s.trust, c.verified
          from claims c join sources s on s.id = c.source_id
         where c.subject_type = %s
         order by c.subject_id, c.field, c.verified desc, s.trust desc, c.created_at desc
        """,
        (subject_type,),
    )
    return cur.fetchall()


def apply_event_values(cur: psycopg.Cursor, event_id: str, values: dict) -> None:
    cur.execute(
        """
        update events set
          name = coalesce(%s, name), date = coalesce(%s, date),
          venue = coalesce(%s, venue), city = coalesce(%s, city)
         where id = %s
        """,
        (values.get("name"), values.get("date"), values.get("venue"), values.get("city"), event_id),
    )


def apply_fighter_values(cur: psycopg.Cursor, fighter_id: str, values: dict) -> None:
    cur.execute(
        """
        update fighters set
          name = coalesce(%s, name), nationality = coalesce(%s, nationality),
          division_id = coalesce(%s, division_id), updated_at = now()
         where id = %s
        """,
        (values.get("name"), values.get("nationality"), values.get("division"), fighter_id),
    )
