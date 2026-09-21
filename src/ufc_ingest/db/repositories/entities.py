"""Escritura de entidades. Todo el SQL vive aquí: los casos de uso no saben de Postgres."""

import psycopg

from ...domain.models import Development, Division, Event, Fight, Fighter, Source

TRUST_BY_TYPE = {"official": 90, "media": 70, "reference": 60, "stats": 70, "manual": 30}


def upsert_source(cur: psycopg.Cursor, source: Source) -> None:
    cur.execute(
        """
        insert into sources (id, name, url, type, trust, retrieved_at)
        values (%s, %s, %s, %s, %s, %s)
        on conflict (id) do update set
          name = excluded.name, url = excluded.url, type = excluded.type,
          retrieved_at = excluded.retrieved_at
        """,
        (
            source.id,
            source.name,
            source.url,
            source.type,
            TRUST_BY_TYPE.get(source.type, 50),
            source.retrieved_at,
        ),
    )


def upsert_division(cur: psycopg.Cursor, division: Division) -> None:
    cur.execute(
        """
        insert into divisions (id, name, limit_lb, ord) values (%s, %s, %s, %s)
        on conflict (id) do update set
          name = excluded.name, limit_lb = excluded.limit_lb, ord = excluded.ord
        """,
        (division.id, division.name, division.limit_lb, division.order),
    )


def upsert_fighter(cur: psycopg.Cursor, fighter: Fighter) -> None:
    cur.execute(
        """
        insert into fighters (id, slug, name, nationality, division_id)
        values (%s, %s, %s, %s, %s)
        on conflict (id) do update set
          slug = excluded.slug, name = excluded.name,
          nationality = excluded.nationality, division_id = excluded.division_id,
          updated_at = now()
        """,
        (fighter.id, fighter.slug, fighter.name, fighter.nationality, fighter.division_id),
    )


def add_alias(cur: psycopg.Cursor, fighter_id: str, alias: str, normalized: str) -> None:
    """La unicidad de `normalized` impide que un alias apunte a dos peleadores."""
    cur.execute(
        """
        insert into fighter_aliases (fighter_id, alias, normalized) values (%s, %s, %s)
        on conflict (normalized) do nothing
        """,
        (fighter_id, alias, normalized),
    )


def upsert_event(cur: psycopg.Cursor, event: Event) -> None:
    cur.execute(
        """
        insert into events (id, slug, name, date, venue, city) values (%s, %s, %s, %s, %s, %s)
        on conflict (id) do update set
          slug = excluded.slug, name = excluded.name, date = excluded.date,
          venue = excluded.venue, city = excluded.city
        """,
        (event.id, event.slug, event.name, event.date, event.venue, event.city),
    )


def upsert_fight(cur: psycopg.Cursor, fight: Fight) -> None:
    cur.execute(
        """
        insert into fights
          (id, slug, event_id, date, division_id, status, winner_id, method,
           method_detail, round, time, title)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (id) do update set
          slug = excluded.slug, status = excluded.status,
          winner_id = excluded.winner_id, method = excluded.method,
          method_detail = excluded.method_detail, round = excluded.round,
          time = excluded.time, title = excluded.title
        """,
        (
            fight.id,
            fight.slug,
            fight.event_id,
            fight.date,
            fight.division_id,
            fight.status,
            fight.winner_id,
            fight.method,
            fight.method_detail,
            fight.round,
            fight.time,
            fight.title,
        ),
    )
    for corner, fighter_id in enumerate(fight.fighter_ids):
        cur.execute(
            """
            insert into fight_participants (fight_id, fighter_id, corner) values (%s, %s, %s)
            on conflict do nothing
            """,
            (fight.id, fighter_id, corner),
        )


def upsert_development(cur: psycopg.Cursor, development: Development) -> None:
    change = development.title_change
    cur.execute(
        """
        insert into developments
          (id, slug, kind, status, date, title, summary, division_id, stakes, holder_id)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        on conflict (id) do update set
          kind = excluded.kind, status = excluded.status, title = excluded.title,
          summary = excluded.summary, division_id = excluded.division_id,
          stakes = excluded.stakes, holder_id = excluded.holder_id
        """,
        (
            development.id,
            development.slug,
            development.kind,
            development.status,
            development.date,
            development.title,
            development.summary,
            change.division_id if change else None,
            change.stakes if change else None,
            change.holder_id if change else None,
        ),
    )
    for ref in development.about:
        cur.execute(
            """
            insert into development_entities (development_id, entity_type, entity_id)
            values (%s, %s, %s) on conflict do nothing
            """,
            (development.id, ref.type, ref.id),
        )
