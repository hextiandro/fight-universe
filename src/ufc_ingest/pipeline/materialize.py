"""Caso de uso: recalcular el valor vigente de cada entidad a partir de sus claims.

Sin esto, el último en escribir gana, aunque su fuente sea peor. Con esto, el valor lo
decide la regla: verificado primero, después la confianza de la fuente, y a igualdad lo
más reciente. Los claims no se tocan: solo se recalcula lo derivado.
"""

import psycopg

from ..db.repositories import claims as claims_repo

# Campos de cada entidad que se derivan de claims.
EVENT_FIELDS = {"name", "date", "venue", "city"}
FIGHTER_FIELDS = {"name", "nationality", "division"}


def run(conn: psycopg.Connection) -> dict[str, int]:
    counts = {"eventos": 0, "peleadores": 0}
    with conn.cursor() as cur:
        for subject, fields, apply, key in (
            ("event", EVENT_FIELDS, claims_repo.apply_event_values, "eventos"),
            ("fighter", FIGHTER_FIELDS, claims_repo.apply_fighter_values, "peleadores"),
        ):
            by_entity: dict[str, dict] = {}
            for row in claims_repo.winning_values(cur, subject):
                if row["field"] in fields:
                    by_entity.setdefault(row["subject_id"], {})[row["field"]] = row["value"]
            for entity_id, values in by_entity.items():
                apply(cur, entity_id, values)
                counts[key] += 1
    conn.commit()
    return counts
