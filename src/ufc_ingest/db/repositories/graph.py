"""Repositorio de lectura: reconstruye el grafo publicado desde el modelo canónico.

Devuelve exactamente la forma que consume la web, con los slugs como identificadores
públicos (los ids internos no salen). La comprobación de paridad compara este resultado
con el dataset semilla: si difieren, la migración perdió algo.
"""

from typing import Any

import psycopg


def build(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("select id, name, limit_lb, ord from divisions order by ord")
        divisions = [
            {"id": r["id"], "name": r["name"], "limitLb": r["limit_lb"], "order": r["ord"]}
            for r in cur.fetchall()
        ]

        cur.execute("select id, name, url, type, retrieved_at from sources order by id")
        sources = [
            {
                "id": r["id"],
                "name": r["name"],
                "url": r["url"] or "",
                "type": r["type"],
                **({"retrievedAt": r["retrieved_at"].isoformat()} if r["retrieved_at"] else {}),
            }
            for r in cur.fetchall()
        ]

        # Claims vigentes por sujeto y campo, con sus fuentes agrupadas.
        cur.execute(
            """
            select subject_type, subject_id, field,
                   min(value::text) as value,
                   array_agg(source_id order by source_rank, source_id) as source_ids,
                   bool_or(verified) as verified,
                   min(note) as note,
                   min(valid_from::text) as valid_from
              from claims
             where source_id <> 'seed-dataset-v1' or field = 'image'
             group by subject_type, subject_id, field
            """
        )
        claims: dict[tuple[str, str, str], dict[str, Any]] = {}
        for r in cur.fetchall():
            claims[(r["subject_type"], r["subject_id"], r["field"])] = r

        cur.execute(
            """
            select f.id, f.slug, f.name, f.nationality, f.division_id,
                   coalesce(
                     array_agg(a.alias order by a.alias) filter (where a.alias is not null), '{}'
                   ) as aliases
              from fighters f
              left join fighter_aliases a on a.fighter_id = f.id
             group by f.id
             order by f.slug
            """
        )
        fighters = []
        for r in cur.fetchall():
            fighter: dict[str, Any] = {"id": r["slug"], "name": r["name"]}
            if r["aliases"]:
                fighter["aliases"] = list(r["aliases"])
            if r["nationality"]:
                fighter["nationality"] = r["nationality"]
            fighter["divisionId"] = r["division_id"]
            record = claims.get(("fighter", r["id"], "record"))
            if record:
                import json as _json

                fighter["record"] = {
                    "value": _json.loads(record["value"]),
                    "asOf": record["valid_from"],
                    "sourceIds": list(record["source_ids"]),
                    "verified": record["verified"],
                    **({"note": record["note"]} if record["note"] else {}),
                }
            fighters.append(fighter)

        cur.execute("select id, slug, name, date, venue, city from events order by date, slug")
        events = []
        for r in cur.fetchall():
            provenance = claims.get(("event", r["id"], "existence"))
            event: dict[str, Any] = {"id": r["slug"], "name": r["name"], "date": r["date"].isoformat()}
            if r["venue"]:
                event["venue"] = r["venue"]
            if r["city"]:
                event["city"] = r["city"]
            event["provenance"] = _provenance(provenance)
            events.append(event)

        cur.execute(
            """
            select b.id, b.slug, b.event_id, e.slug as event_slug, b.date, b.division_id,
                   b.winner_id, w.slug as winner_slug, b.method, b.method_detail, b.round, b.time, b.title,
                   array_agg(p.fighter_id order by p.corner) as fighter_ids,
                   array_agg(pf.slug order by p.corner) as fighter_slugs
              from fights b
              join events e on e.id = b.event_id
              join fight_participants p on p.fight_id = b.id
              join fighters pf on pf.id = p.fighter_id
              left join fighters w on w.id = b.winner_id
             group by b.id, e.slug, w.slug
             order by b.date, b.id
            """
        )
        fights = []
        for r in cur.fetchall():
            fight: dict[str, Any] = {
                "id": r["slug"],
                "eventId": r["event_slug"],
                "date": r["date"].isoformat(),
                "divisionId": r["division_id"],
                "fighterIds": list(r["fighter_slugs"]),
                "winnerId": r["winner_slug"],
                "method": r["method"],
            }
            if r["method_detail"]:
                fight["methodDetail"] = r["method_detail"]
            if r["round"] is not None:
                fight["round"] = r["round"]
            if r["time"]:
                fight["time"] = r["time"]
            if r["title"]:
                fight["title"] = r["title"]
            fight["provenance"] = _provenance(claims.get(("fight", r["id"], "result")))
            fights.append(fight)

        # Relaciones de cada novedad, con los ids internos traducidos a slugs públicos.
        cur.execute(
            """
            select de.development_id, de.entity_type,
                   coalesce(f.slug, e.slug, b.slug, de.entity_id) as target
              from development_entities de
              left join fighters f on de.entity_type = 'fighter' and f.id = de.entity_id
              left join events e on de.entity_type = 'event' and e.id = de.entity_id
              left join fights b on de.entity_type = 'fight' and b.id = de.entity_id
            """
        )
        about: dict[str, list[dict[str, str]]] = {}
        for r in cur.fetchall():
            about.setdefault(r["development_id"], []).append({"type": r["entity_type"], "id": r["target"]})

        cur.execute(
            """
            select d.id, d.slug, d.kind, d.status, d.date, d.title, d.summary,
                   d.division_id, d.stakes, d.holder_id, h.slug as holder_slug
              from developments d
              left join fighters h on h.id = d.holder_id
             order by d.date, d.slug
            """
        )
        developments = []
        for r in cur.fetchall():
            development: dict[str, Any] = {
                "id": r["slug"],
                "kind": r["kind"],
                "status": r["status"],
                "date": r["date"].isoformat(),
                "title": r["title"],
                "summary": r["summary"],
                "about": about.get(r["id"], []),
            }
            if r["division_id"]:
                development["titleChange"] = {
                    "divisionId": r["division_id"],
                    "stakes": r["stakes"],
                    "holderId": r["holder_slug"],
                }
            development["provenance"] = _provenance(claims.get(("development", r["id"], "existence")))
            developments.append(development)

    return {
        "divisions": divisions,
        "sources": sources,
        "fighters": fighters,
        "events": events,
        "fights": fights,
        "developments": developments,
    }


def _provenance(claim: dict[str, Any] | None) -> dict[str, Any]:
    if not claim:
        return {"sourceIds": [], "verified": False}
    out: dict[str, Any] = {"sourceIds": list(claim["source_ids"]), "verified": claim["verified"]}
    if claim["note"]:
        out["note"] = claim["note"]
    return out
