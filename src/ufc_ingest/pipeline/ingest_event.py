"""Caso de uso: ingerir un evento de una fuente.

Aquí el pipeline empieza a escribir, con una política explícita:

- Lo que se resuelve por identificador externo o por nombre exacto (niveles 1 y 2) se
  aplica solo.
- Todo lo demás va a la cola de revisión: altas de peleadores, menciones ambiguas y
  parecidos, por buenos que sean.

Ninguna fuente da de alta una entidad por su cuenta.
"""

from dataclasses import dataclass, field

import psycopg

from ..connectors.base import Candidate, Mention
from ..connectors.wikipedia_events import WikipediaEvents
from ..db.repositories import claims as claims_repo
from ..db.repositories import entities as entities_repo
from ..db.repositories import review as review_repo
from ..db.repositories.lookup import DbLookup
from ..domain.ids import make_id
from ..domain.models import Claim, Event, Fight, Provenance
from ..domain.text import normalize
from ..resolution.resolver import EntityResolver, Resolution

ACTOR = "pipeline:wikipedia-events"


@dataclass
class IngestReport:
    event: str
    applied: list[str] = field(default_factory=list)
    queued: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def line(self) -> str:
        return (
            f"aplicados: {len(self.applied)} · a revisión: {len(self.queued)} · "
            f"sin cambios: {len(self.skipped)}"
        )


def _slug(text: str) -> str:
    return normalize(text).replace(" ", "-")


def run(event_title: str, conn: psycopg.Connection, source_id: str = "wikipedia-events") -> IngestReport:
    connector = WikipediaEvents()
    doc = connector.fetch_page(event_title)
    candidates = list(connector.extract(doc))
    report = IngestReport(event=event_title)

    with conn.cursor() as cur:
        entities_repo.upsert_source(
            cur,
            __import__("ufc_ingest.domain.models", fromlist=["Source"]).Source(
                id=source_id,
                name="Wikipedia — eventos de UFC",
                url="https://en.wikipedia.org",
                type="reference",
            ),
        )
        resolver = EntityResolver(DbLookup(cur))

        event_candidate = next((c for c in candidates if c.kind == "event"), None)
        event_id = _apply_event(cur, event_candidate, report, source_id) if event_candidate else None
        event_date = event_candidate.payload.get("date") if event_candidate else None

        # Peleadores: lo desconocido y lo dudoso se encola; nada se da de alta solo.
        resolved: dict[str, Resolution] = {}
        for mention in _fighter_mentions(candidates):
            resolution = resolver.resolve(mention)
            resolved[mention.text] = resolution
            if resolution.needs_review:
                _queue_fighter(cur, mention, resolution, report, source_id)

        if event_id and event_date:
            for candidate in (c for c in candidates if c.kind == "fight"):
                _handle_fight(cur, candidate, event_id, event_date, resolved, report, source_id)

    conn.commit()
    return report


def _fighter_mentions(candidates: list[Candidate]) -> list[Mention]:
    seen: dict[str, Mention] = {}
    for candidate in candidates:
        for mention in candidate.mentions:
            if mention.entity_type == "fighter":
                seen.setdefault(mention.text, mention)
    return list(seen.values())


def _apply_event(
    cur: psycopg.Cursor, candidate: Candidate, report: IngestReport, source_id: str
) -> str | None:
    payload = candidate.payload
    if not payload.get("date"):
        report.queued.append(f"evento {payload['name']} (sin fecha legible)")
        review_repo.enqueue(
            cur,
            {"kind": "event", "key": f"event:{payload['name']}", **payload},
            "no se pudo leer la fecha",
            candidate.confidence,
        )
        return None

    slug = _slug(payload["name"])
    existing = review_repo.event_id_by_slug(cur, slug)
    event_id = existing or make_id("event", slug)
    entities_repo.upsert_event(
        cur,
        Event(
            id=event_id,
            slug=slug,
            name=payload["name"],
            date=payload["date"],
            venue=payload.get("venue"),
            city=payload.get("city"),
        ),
    )
    provenance = Provenance(source_ids=[source_id], verified=False)
    for claim_field, value in (
        ("name", payload["name"]),
        ("date", payload["date"]),
        ("venue", payload.get("venue")),
        ("city", payload.get("city")),
    ):
        if value is not None:
            claims_repo.record(
                cur,
                Claim(
                    subject_type="event",
                    subject_id=event_id,
                    field=claim_field,
                    value=value,
                    provenance=provenance,
                ),
                source_id,
            )
    (report.skipped if existing else report.applied).append(f"evento {payload['name']}")
    review_repo.log(cur, ACTOR, "upsert", f"event:{event_id}", payload)
    return event_id


def _queue_fighter(
    cur: psycopg.Cursor, mention: Mention, resolution: Resolution, report: IngestReport, source_id: str
) -> None:
    candidate = {
        "kind": "fighter",
        "key": f"fighter:{mention.text}",
        "name": mention.text,
        "hints": mention.hints,
        "proposal": {"entityId": resolution.entity_id, "name": resolution.name, "level": resolution.level},
        "candidates": [{"id": c.entity_id, "name": c.name, "score": c.score} for c in resolution.candidates],
        "sourceId": source_id,
    }
    reason = "alta de peleador" if resolution.status == "unknown" else resolution.reason
    if review_repo.enqueue(cur, candidate, reason, resolution.confidence) is not None:
        report.queued.append(f"peleador {mention.text} ({reason})")


def _handle_fight(
    cur: psycopg.Cursor,
    candidate: Candidate,
    event_id: str,
    event_date: str,
    resolved: dict[str, Resolution],
    report: IngestReport,
    source_id: str,
) -> None:
    payload = candidate.payload
    names: list[str] = payload["fighters"]
    resolutions = [resolved.get(name) for name in names]

    automatic = all(r and r.status == "matched" and not r.needs_review for r in resolutions)
    if not automatic:
        pending = [n for n, r in zip(names, resolutions, strict=True) if not r or r.needs_review]
        review_repo.enqueue(
            cur,
            {
                "kind": "fight",
                "key": f"fight:{event_id}:{'|'.join(names)}",
                "eventId": event_id,
                "sourceId": source_id,
                **payload,
            },
            f"peleadores pendientes: {', '.join(pending)}",
            candidate.confidence,
        )
        report.queued.append(f"pelea {names[0]} vs {names[1]}")
        return

    fighter_ids = [r.entity_id for r in resolutions if r and r.entity_id]
    slug = f"{_slug(payload['eventTitle'])}-{_slug(names[0]).split('-')[-1]}-{_slug(names[1]).split('-')[-1]}"
    fight_id = make_id("fight", slug)
    # Se actualiza siempre: los datos de una pelea cambian (resultado, posición en la
    # cartelera) y el upsert es idempotente.
    existed = review_repo.fight_exists(cur, fight_id)

    winner = payload.get("winner")
    entities_repo.upsert_fight(
        cur,
        Fight(
            id=fight_id,
            slug=slug,
            event_id=event_id,
            date=event_date,
            division_id=payload["divisionId"],
            status=payload.get("status", "completed"),
            card_position=payload.get("cardPosition", 0),
            fighter_ids=fighter_ids,  # type: ignore[arg-type]
            winner_id=fighter_ids[names.index(winner)] if winner in names else None,
            method=payload["method"],
            method_detail=payload.get("methodDetail"),
            round=payload.get("round"),
            time=payload.get("time"),
        ),
    )
    claims_repo.record(
        cur,
        Claim(
            subject_type="fight",
            subject_id=fight_id,
            field="result",
            value={"winner": winner, "method": payload["method"], "round": payload.get("round")},
            valid_from=event_date,
            provenance=Provenance(source_ids=[source_id], verified=False),
        ),
        source_id,
    )
    review_repo.log(cur, ACTOR, "upsert", f"fight:{fight_id}", payload)
    (report.skipped if existed else report.applied).append(f"pelea {names[0]} vs {names[1]}")
