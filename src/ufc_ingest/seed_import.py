"""Importa el dataset semilla (JSON exportado por la web) al modelo canónico.

Es el corte 1: los datos dejan de vivir en archivos TypeScript y pasan a Postgres, sin
perder nada. Cada valor no trivial entra además como `claim` con su fuente, su confianza
y su marca de verificado, que es lo que luego alimenta el "sin verificar" del panel.

Es idempotente: reimportar la misma semilla no duplica nada.
"""

import json
from pathlib import Path
from typing import Any

import psycopg

from .ids import make_id, normalize

MANUAL_SOURCE = "seed-dataset-v1"


def _claim(
    cur: psycopg.Cursor,
    subject_type: str,
    subject_id: str,
    field: str,
    value: Any,
    source_ids: list[str],
    verified: bool,
    note: str | None = None,
    valid_from: str | None = None,
) -> None:
    """Un claim por fuente: el mismo hecho respaldado por dos medios deja dos rastros."""
    for rank, source_id in enumerate(source_ids or [MANUAL_SOURCE]):
        cur.execute(
            """
            insert into claims
              (subject_type, subject_id, field, value, source_id, source_rank,
               confidence, verified, note, valid_from)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (subject_type, subject_id, field, source_id, md5(value::text))
            do update set
              source_rank = excluded.source_rank, confidence = excluded.confidence,
              verified = excluded.verified, note = excluded.note, valid_from = excluded.valid_from
            """,
            (
                subject_type,
                subject_id,
                field,
                json.dumps(value, ensure_ascii=False),
                source_id,
                rank,
                90 if verified else 50,
                verified,
                note,
                valid_from,
            ),
        )


def run(seed_path: Path, conn: psycopg.Connection) -> dict[str, int]:
    seed = json.loads(seed_path.read_text())
    counts: dict[str, int] = {}
    # El slug de la semilla se conserva: los enlaces ya compartidos siguen funcionando.
    fighter_id = {f["id"]: make_id("fighter", f["id"]) for f in seed["fighters"]}
    event_id = {e["id"]: make_id("event", e["id"]) for e in seed["events"]}
    fight_id = {f["id"]: make_id("fight", f["id"]) for f in seed["fights"]}
    development_id = {d["id"]: make_id("development", d["id"]) for d in seed["developments"]}

    with conn.cursor() as cur:
        # Fuentes: la semilla manual también es una fuente, con poca confianza.
        cur.execute(
            """
            insert into sources (id, name, url, type, trust) values (%s, %s, %s, %s, %s)
            on conflict (id) do update set name = excluded.name, url = excluded.url
            """,
            (MANUAL_SOURCE, "Dataset semilla v1 (compilación manual)", None, "manual", 30),
        )
        for s in seed["sources"]:
            cur.execute(
                """
                insert into sources (id, name, url, type, trust, retrieved_at)
                values (%s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                  name = excluded.name, url = excluded.url, type = excluded.type,
                  retrieved_at = excluded.retrieved_at
                """,
                (
                    s["id"],
                    s["name"],
                    s["url"] or None,
                    s["type"],
                    {"official": 90, "media": 70, "reference": 60, "stats": 70}.get(s["type"], 50),
                    s.get("retrievedAt"),
                ),
            )
        counts["sources"] = len(seed["sources"]) + 1

        for d in seed["divisions"]:
            cur.execute(
                """
                insert into divisions (id, name, limit_lb, ord) values (%s, %s, %s, %s)
                on conflict (id) do update set
                  name = excluded.name, limit_lb = excluded.limit_lb, ord = excluded.ord
                """,
                (d["id"], d["name"], d["limitLb"], d["order"]),
            )
        counts["divisions"] = len(seed["divisions"])

        for f in seed["fighters"]:
            fid = fighter_id[f["id"]]
            cur.execute(
                """
                insert into fighters (id, slug, name, nationality, division_id) values (%s, %s, %s, %s, %s)
                on conflict (id) do update set
                  slug = excluded.slug, name = excluded.name,
                  nationality = excluded.nationality, division_id = excluded.division_id,
                  updated_at = now()
                """,
                (fid, f["id"], f["name"], f.get("nationality"), f["divisionId"]),
            )
            for alias in f.get("aliases", []):
                cur.execute(
                    """
                    insert into fighter_aliases (fighter_id, alias, normalized) values (%s, %s, %s)
                    on conflict (normalized) do nothing
                    """,
                    (fid, alias, normalize(alias)),
                )
            record = f.get("record")
            if record:
                _claim(
                    cur,
                    "fighter",
                    fid,
                    "record",
                    record["value"],
                    record["sourceIds"],
                    record["verified"],
                    record.get("note"),
                    record["asOf"],
                )
            if f.get("image"):
                _claim(cur, "fighter", fid, "image", f["image"], [MANUAL_SOURCE], True)
        counts["fighters"] = len(seed["fighters"])

        for e in seed["events"]:
            eid = event_id[e["id"]]
            cur.execute(
                """
                insert into events (id, slug, name, date, venue, city) values (%s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                  slug = excluded.slug, name = excluded.name, date = excluded.date,
                  venue = excluded.venue, city = excluded.city
                """,
                (eid, e["id"], e["name"], e["date"], e.get("venue"), e.get("city")),
            )
            p = e["provenance"]
            _claim(
                cur,
                "event",
                eid,
                "existence",
                {"name": e["name"], "date": e["date"]},
                p["sourceIds"],
                p["verified"],
                p.get("note"),
            )
        counts["events"] = len(seed["events"])

        for f in seed["fights"]:
            bid = fight_id[f["id"]]
            cur.execute(
                """
                insert into fights
                  (id, slug, event_id, date, division_id, winner_id, method,
                   method_detail, round, time, title)
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                on conflict (id) do update set
                  slug = excluded.slug,
                  winner_id = excluded.winner_id, method = excluded.method,
                  method_detail = excluded.method_detail, round = excluded.round,
                  time = excluded.time, title = excluded.title
                """,
                (
                    bid,
                    f["id"],
                    event_id[f["eventId"]],
                    f["date"],
                    f["divisionId"],
                    fighter_id[f["winnerId"]] if f.get("winnerId") else None,
                    f["method"],
                    f.get("methodDetail"),
                    f.get("round"),
                    f.get("time"),
                    f.get("title"),
                ),
            )
            for corner, fighter_slug in enumerate(f["fighterIds"]):
                cur.execute(
                    """
                    insert into fight_participants (fight_id, fighter_id, corner) values (%s, %s, %s)
                    on conflict do nothing
                    """,
                    (bid, fighter_id[fighter_slug], corner),
                )
            p = f["provenance"]
            _claim(
                cur,
                "fight",
                bid,
                "result",
                {"winnerId": f.get("winnerId"), "method": f["method"], "round": f.get("round")},
                p["sourceIds"],
                p["verified"],
                p.get("note"),
                f["date"],
            )
        counts["fights"] = len(seed["fights"])

        for d in seed["developments"]:
            did = development_id[d["id"]]
            change = d.get("titleChange") or {}
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
                    did,
                    d["id"],
                    d["kind"],
                    d["status"],
                    d["date"],
                    d["title"],
                    d["summary"],
                    change.get("divisionId"),
                    change.get("stakes"),
                    fighter_id[change["holderId"]] if change.get("holderId") else None,
                ),
            )
            for ref in d["about"]:
                target = {
                    "fighter": fighter_id,
                    "event": event_id,
                    "fight": fight_id,
                }.get(ref["type"], {}).get(ref["id"], ref["id"])
                cur.execute(
                    """
                    insert into development_entities (development_id, entity_type, entity_id)
                    values (%s, %s, %s) on conflict do nothing
                    """,
                    (did, ref["type"], target),
                )
            p = d["provenance"]
            _claim(
                cur,
                "development",
                did,
                "existence",
                {"kind": d["kind"], "status": d["status"], "title": d["title"]},
                p["sourceIds"],
                p["verified"],
                p.get("note"),
                d["date"],
            )
        counts["developments"] = len(seed["developments"])

    conn.commit()
    return counts
