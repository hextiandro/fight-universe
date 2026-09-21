"""Caso de uso: importar el dataset semilla al modelo canónico.

Tres pasos separados: leer el JSON, traducirlo al dominio y persistirlo por repositorios.
Este módulo no contiene SQL; el SQL vive en `db/repositories`.

Es idempotente: reimportar la misma semilla no duplica nada.
"""

import json
from pathlib import Path
from typing import Any

import psycopg

from ..db.repositories import claims as claims_repo
from ..db.repositories import entities as entities_repo
from ..domain.ids import make_id
from ..domain.models import (
    Claim,
    Development,
    Division,
    EntityRef,
    Event,
    Fight,
    Fighter,
    Provenance,
    Source,
    TitleChange,
)
from ..domain.text import normalize

MANUAL_SOURCE = "seed-dataset-v1"


class SeedMapper:
    """Traduce el JSON de la web al dominio, asignando ids internos estables.

    Los slugs de la semilla se conservan como identificador público: los enlaces ya
    compartidos siguen funcionando aunque el id interno sea otro.
    """

    def __init__(self, seed: dict[str, Any]) -> None:
        self.seed = seed
        self.fighter_ids = {f["id"]: make_id("fighter", f["id"]) for f in seed["fighters"]}
        self.event_ids = {e["id"]: make_id("event", e["id"]) for e in seed["events"]}
        self.fight_ids = {f["id"]: make_id("fight", f["id"]) for f in seed["fights"]}
        self.development_ids = {d["id"]: make_id("development", d["id"]) for d in seed["developments"]}

    def provenance(self, raw: dict[str, Any]) -> Provenance:
        return Provenance(
            source_ids=raw.get("sourceIds", []),
            verified=raw.get("verified", False),
            note=raw.get("note"),
        )

    def sources(self) -> list[Source]:
        seed_source = Source(id=MANUAL_SOURCE, name="Dataset semilla v1 (compilación manual)", type="manual")
        return [seed_source] + [
            Source(
                id=s["id"],
                name=s["name"],
                url=s["url"] or None,
                type=s["type"],
                retrieved_at=s.get("retrievedAt"),
            )
            for s in self.seed["sources"]
        ]

    def divisions(self) -> list[Division]:
        return [
            Division(id=d["id"], name=d["name"], limit_lb=d["limitLb"], order=d["order"])
            for d in self.seed["divisions"]
        ]

    def fighters(self) -> list[tuple[Fighter, list[Claim]]]:
        out = []
        for f in self.seed["fighters"]:
            fid = self.fighter_ids[f["id"]]
            fighter = Fighter(
                id=fid,
                slug=f["id"],
                name=f["name"],
                nationality=f.get("nationality"),
                division_id=f["divisionId"],
                aliases=f.get("aliases", []),
            )
            facts: list[Claim] = [
                Claim(
                    subject_type="fighter",
                    subject_id=fid,
                    field=field,
                    value=value,
                    provenance=Provenance(source_ids=[MANUAL_SOURCE], verified=True),
                )
                for field, value in (
                    ("name", f["name"]),
                    ("division", f["divisionId"]),
                    ("nationality", f.get("nationality")),
                )
                if value is not None
            ]
            if record := f.get("record"):
                facts.append(
                    Claim(
                        subject_type="fighter",
                        subject_id=fid,
                        field="record",
                        value=record["value"],
                        valid_from=record["asOf"],
                        provenance=self.provenance(record),
                    )
                )
            if image := f.get("image"):
                facts.append(
                    Claim(
                        subject_type="fighter",
                        subject_id=fid,
                        field="image",
                        value=image,
                        provenance=Provenance(source_ids=[MANUAL_SOURCE], verified=True),
                    )
                )
            out.append((fighter, facts))
        return out

    def events(self) -> list[tuple[Event, list[Claim]]]:
        out = []
        for e in self.seed["events"]:
            eid = self.event_ids[e["id"]]
            event = Event(
                id=eid,
                slug=e["id"],
                name=e["name"],
                date=e["date"],
                venue=e.get("venue"),
                city=e.get("city"),
            )
            provenance = self.provenance(e["provenance"])
            facts = [
                Claim(subject_type="event", subject_id=eid, field=field, value=value, provenance=provenance)
                for field, value in (
                    ("name", e["name"]),
                    ("date", e["date"]),
                    ("venue", e.get("venue")),
                    ("city", e.get("city")),
                )
                if value is not None
            ]
            out.append((event, facts))
        return out

    def fights(self) -> list[tuple[Fight, list[Claim]]]:
        out = []
        for f in self.seed["fights"]:
            bid = self.fight_ids[f["id"]]
            fight = Fight(
                id=bid,
                slug=f["id"],
                event_id=self.event_ids[f["eventId"]],
                date=f["date"],
                division_id=f["divisionId"],
                fighter_ids=[self.fighter_ids[s] for s in f["fighterIds"]],
                winner_id=self.fighter_ids[f["winnerId"]] if f.get("winnerId") else None,
                method=f["method"],
                method_detail=f.get("methodDetail"),
                round=f.get("round"),
                time=f.get("time"),
                title=f.get("title"),
            )
            fact = Claim(
                subject_type="fight",
                subject_id=bid,
                field="result",
                value={
                    "winnerId": f.get("winnerId"),
                    "method": f["method"],
                    "round": f.get("round"),
                },
                valid_from=f["date"],
                provenance=self.provenance(f["provenance"]),
            )
            out.append((fight, [fact]))
        return out

    def developments(self) -> list[tuple[Development, list[Claim]]]:
        targets = {"fighter": self.fighter_ids, "event": self.event_ids, "fight": self.fight_ids}
        out = []
        for d in self.seed["developments"]:
            did = self.development_ids[d["id"]]
            change = d.get("titleChange")
            development = Development(
                id=did,
                slug=d["id"],
                kind=d["kind"],
                status=d["status"],
                date=d["date"],
                title=d["title"],
                summary=d["summary"],
                about=[
                    EntityRef(
                        type=ref["type"],
                        id=targets.get(ref["type"], {}).get(ref["id"], ref["id"]),
                    )
                    for ref in d["about"]
                ],
                title_change=TitleChange(
                    division_id=change["divisionId"],
                    stakes=change["stakes"],
                    holder_id=self.fighter_ids[change["holderId"]] if change.get("holderId") else None,
                )
                if change
                else None,
            )
            fact = Claim(
                subject_type="development",
                subject_id=did,
                field="existence",
                value={"kind": d["kind"], "status": d["status"], "title": d["title"]},
                valid_from=d["date"],
                provenance=self.provenance(d["provenance"]),
            )
            out.append((development, [fact]))
        return out


def run(seed_path: Path, conn: psycopg.Connection) -> dict[str, int]:
    mapper = SeedMapper(json.loads(seed_path.read_text()))
    counts: dict[str, int] = {}

    with conn.cursor() as cur:
        sources = mapper.sources()
        for source in sources:
            entities_repo.upsert_source(cur, source)
        counts["sources"] = len(sources)

        divisions = mapper.divisions()
        for division in divisions:
            entities_repo.upsert_division(cur, division)
        counts["divisions"] = len(divisions)

        groups = [
            ("fighters", mapper.fighters, entities_repo.upsert_fighter),
            ("events", mapper.events, entities_repo.upsert_event),
            ("fights", mapper.fights, entities_repo.upsert_fight),
            ("developments", mapper.developments, entities_repo.upsert_development),
        ]
        for name, load, upsert in groups:
            items = load()
            for entity, facts in items:
                upsert(cur, entity)
                if name == "fighters":
                    for alias in entity.aliases:
                        entities_repo.add_alias(cur, entity.id, alias, normalize(alias))
                for fact in facts:
                    claims_repo.record(cur, fact, MANUAL_SOURCE)
            counts[name] = len(items)

    conn.commit()
    return counts
