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
