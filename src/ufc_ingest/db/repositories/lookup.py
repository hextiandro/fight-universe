"""Catálogo de entidades para la resolución. Aquí vive el SQL; el resolutor no lo ve."""

import psycopg

from ...resolution.resolver import Match

TABLES = {"fighter": "fighters", "event": "events"}


class DbLookup:
    def __init__(self, cur: psycopg.Cursor) -> None:
        self.cur = cur

    def by_external_id(self, entity_type: str, system: str, value: str) -> Match | None:
        if entity_type != "fighter":
            return None
        self.cur.execute(
            """
            select f.id, f.name from fighter_external_ids x
              join fighters f on f.id = x.fighter_id
             where x.system = %s and x.value = %s
            """,
            (system, value),
        )
        row = self.cur.fetchone()
        return Match(row["id"], row["name"], 1.0) if row else None

    def by_name(self, entity_type: str, normalized: str) -> list[Match]:
        if entity_type == "fighter":
            self.cur.execute(
                """
                select id, name from fighters
                 where lower(unaccent(name)) = %s
                union
                select f.id, f.name from fighter_aliases a
                  join fighters f on f.id = a.fighter_id
                 where a.normalized = %s
                """,
                (normalized, normalized),
            )
        elif entity_type == "event":
            self.cur.execute(
                """
                select id, name from events where lower(unaccent(name)) = %s
                union
                select e.id, e.name from event_aliases a
                  join events e on e.id = a.event_id
                 where a.normalized = %s
                """,
                (normalized, normalized),
            )
        else:
            return []
        return [Match(r["id"], r["name"], 1.0) for r in self.cur.fetchall()]

    def similar(self, entity_type: str, normalized: str, limit: int = 5) -> list[Match]:
        table = TABLES.get(entity_type)
        if not table:
            return []
        self.cur.execute(
            f"""
            select id, name, similarity(lower(unaccent(name)), %s) as score
              from {table}
             where similarity(lower(unaccent(name)), %s) > 0.3
             order by score desc limit %s
            """,  # noqa: S608 - tabla de una lista fija
            (normalized, normalized, limit),
        )
        return [Match(r["id"], r["name"], float(r["score"])) for r in self.cur.fetchall()]
