"""Caso de uso: aplicar lo que una persona aprueba en la cola de revisión.

Aprobar es la única vía por la que una entidad nueva entra en el grafo. Cada decisión
queda registrada en `change_log`, con quién y cuándo.
"""

from typing import Any

import psycopg

from ..connectors.base import Mention
from ..db.repositories import claims as claims_repo
from ..db.repositories import entities as entities_repo
from ..db.repositories import review as review_repo
from ..db.repositories.lookup import DbLookup
from ..domain.ids import make_id
from ..domain.models import Claim, Fight, Fighter, Provenance
from ..domain.text import normalize
from ..resolution.resolver import EntityResolver


def describe(item: dict[str, Any]) -> list[str]:
    """Lo que ve quien revisa: el hecho, de dónde sale y por qué no entró solo."""
    candidate = item["candidate"]
    kind = candidate.get("kind")
    lines = []
    if kind == "fighter":
        hints = candidate.get("hints", {})
        lines.append(f"ALTA DE PELEADOR  {candidate['name']}")
        lines.append(f"  división: {hints.get('division', '—')}  ·  wikipedia: {hints.get('wikipedia', '—')}")
        if proposal := candidate.get("proposal", {}).get("name"):
            lines.append(f"  ¿es el mismo que «{proposal}»? (nivel {candidate['proposal'].get('level')})")
        for option in candidate.get("candidates", [])[:3]:
            lines.append(f"  parecido: {option['name']} ({option['score']:.2f})")
    elif kind == "fight":
        p = candidate
        detail = f" ({p['methodDetail']})" if p.get("methodDetail") else ""
        winner = f"gana {p['winner']}" if p.get("winner") else "programada"
        lines.append(f"PELEA  {p['fighters'][0]} vs {p['fighters'][1]} · {p['divisionId']}")
        lines.append(f"  {p['method']}{detail} · R{p.get('round')} · {p.get('time')} · {winner}")
    else:
        lines.append(f"{kind}  {candidate.get('name', '')}")
    lines.append(f"  motivo: {item['reason']}  ·  confianza {item['confidence']}")
    return lines


def approve(cur: psycopg.Cursor, item: dict[str, Any], actor: str) -> str:
    candidate = item["candidate"]
    kind = candidate.get("kind")
    if kind == "fighter":
        return _approve_fighter(cur, candidate, actor)
    if kind == "fight":
        return _approve_fight(cur, candidate, actor)
    raise ValueError(f"no sé aprobar candidatos de tipo {kind}")


def _approve_fighter(cur: psycopg.Cursor, candidate: dict[str, Any], actor: str) -> str:
    name = candidate["name"]
    hints = candidate.get("hints", {})
    slug = normalize(name).replace(" ", "-")
    fighter_id = make_id("fighter", slug)

    entities_repo.upsert_fighter(
        cur,
        Fighter(id=fighter_id, slug=slug, name=name, division_id=hints.get("division", "heavyweight")),
    )
    # El id externo evita que el mismo peleador vuelva a entrar como alta: a partir de
    # ahora se resuelve por nivel 1, sin depender del nombre.
    if wikipedia := hints.get("wikipedia"):
        review_repo.add_external_id(cur, fighter_id, "wikipedia", wikipedia)
    claims_repo.record(
        cur,
        Claim(
            subject_type="fighter",
            subject_id=fighter_id,
            field="existence",
            value={"name": name, "division": hints.get("division")},
            provenance=Provenance(source_ids=[candidate.get("sourceId", "manual")], verified=False),
        ),
        "manual",
    )
    review_repo.log(cur, actor, "insert", f"fighter:{fighter_id}", {"name": name})
    return f"alta de {name}"


def _approve_fight(cur: psycopg.Cursor, candidate: dict[str, Any], actor: str) -> str:
    names: list[str] = candidate["fighters"]
    resolver = EntityResolver(DbLookup(cur))
    ids = []
    for name in names:
        resolution = resolver.resolve(Mention(entity_type="fighter", text=name))
        if not resolution.entity_id:
            raise LookupError(f"«{name}» todavía no existe: apruébalo antes que la pelea")
        ids.append(resolution.entity_id)

    date = review_repo.event_date(cur, candidate["eventId"])
    if not date:
        raise LookupError("el evento de esta pelea no existe")

    slug_parts = [normalize(n).split(" ")[-1] for n in names]
    slug = f"{normalize(candidate['eventTitle']).replace(' ', '-')}-{'-'.join(slug_parts)}"
    fight_id = make_id("fight", slug)
    winner = candidate.get("winner")

    entities_repo.upsert_fight(
        cur,
        Fight(
            id=fight_id,
            slug=slug,
            event_id=candidate["eventId"],
            date=date,
            division_id=candidate["divisionId"],
            fighter_ids=ids,
            winner_id=ids[names.index(winner)] if winner in names else None,
            method=candidate["method"],
            method_detail=candidate.get("methodDetail"),
            round=candidate.get("round"),
            time=candidate.get("time"),
        ),
    )
    claims_repo.record(
        cur,
        Claim(
            subject_type="fight",
            subject_id=fight_id,
            field="result",
            value={"winner": winner, "method": candidate["method"]},
            valid_from=date,
            provenance=Provenance(source_ids=[candidate.get("sourceId", "manual")], verified=False),
        ),
        "manual",
    )
    review_repo.log(cur, actor, "insert", f"fight:{fight_id}", {"fighters": names})
    return f"pelea {names[0]} vs {names[1]}"


def bulk_approve_new_fighters(cur: psycopg.Cursor, items: list[dict[str, Any]], actor: str) -> list[str]:
    """Aprobación en bloque, solo para la carga inicial.

    Se limita a las altas **sin ambigüedad**: peleador desconocido, con su página de
    Wikipedia y sin candidatos parecidos. Todo lo dudoso sigue pasando por una persona.
    El actor distinto deja constancia en el registro de qué entró por esta vía.
    """
    from ..db.repositories import review as repo

    approved = []
    for item in items:
        candidate = item["candidate"]
        unambiguous = (
            candidate.get("kind") == "fighter"
            and not candidate.get("candidates")
            and not candidate.get("proposal", {}).get("entityId")
            and candidate.get("hints", {}).get("wikipedia")
        )
        if not unambiguous:
            continue
        approved.append(approve(cur, item, actor))
        repo.decide(cur, item["id"], "approved", actor)
    return approved
