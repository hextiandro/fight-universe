"""Resolución de entidades: de una mención a una entidad del grafo.

La regla que sostiene todo: **la identidad no se deriva del texto que llega**. Una fuente
trae "Ilia", "Ilia Topuria" o "Topuria"; aquí se decide a qué nodo se refiere, o se manda a
revisión. Ninguna fuente crea entidades por su cuenta.

Este módulo no sabe de Postgres: recibe un `Lookup`, que es un puerto.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..connectors.base import Mention
from ..domain.text import normalize

Status = Literal["matched", "ambiguous", "unknown"]


@dataclass(frozen=True)
class Match:
    entity_id: str
    name: str
    score: float


class Lookup(Protocol):
    """Lo que el resolutor necesita saber del catálogo, sin saber cómo se guarda."""

    def by_external_id(self, entity_type: str, system: str, value: str) -> Match | None: ...

    def by_name(self, entity_type: str, normalized: str) -> list[Match]: ...

    def similar(self, entity_type: str, normalized: str, limit: int = 5) -> list[Match]: ...


@dataclass
class Resolution:
    mention: Mention
    status: Status
    entity_id: str | None = None
    name: str | None = None
    #  1 id externo · 2 nombre o alias · 3 contexto · 4 aproximado
    level: int | None = None
    confidence: int = 0
    reason: str = ""
    candidates: list[Match] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        """Solo el nivel 1 y el 2 entran solos; lo demás lo decide una persona."""
        return self.status != "matched" or (self.level or 9) > 2


# Umbral por debajo del cual ni siquiera se propone un candidato.
SIMILARITY_FLOOR = 0.45
# Con contexto (misma división) basta menos parecido para proponer, pero nunca para decidir.
CONTEXT_FLOOR = 0.6


class EntityResolver:
    def __init__(self, lookup: Lookup) -> None:
        self.lookup = lookup

    def resolve(self, mention: Mention) -> Resolution:
        kind = mention.entity_type
        normalized = normalize(mention.text)

        # Nivel 1: identificador externo. Es el único que no depende del nombre.
        for system, value in mention.hints.items():
            if system not in {"wikipedia", "wikidata", "provider"} or not isinstance(value, str):
                continue
            if match := self.lookup.by_external_id(kind, system, value):
                return Resolution(
                    mention,
                    "matched",
                    match.entity_id,
                    match.name,
                    1,
                    99,
                    f"id externo {system}:{value}",
                )

        # Nivel 2: nombre o alias normalizado, y con un único dueño.
        exact = self.lookup.by_name(kind, normalized)
        if len(exact) == 1:
            match = exact[0]
            return Resolution(mention, "matched", match.entity_id, match.name, 2, 90, "nombre o alias exacto")
        if len(exact) > 1:
            return Resolution(
                mention,
                "ambiguous",
                level=2,
                confidence=40,
                reason=f"{len(exact)} entidades comparten ese nombre",
                candidates=exact,
            )

        # Nivel 3 y 4: parecido. El contexto sube la confianza, nunca decide solo.
        similar = [m for m in self.lookup.similar(kind, normalized) if m.score >= SIMILARITY_FLOOR]
        if not similar:
            return Resolution(mention, "unknown", level=4, confidence=0, reason="sin candidatos")

        best = similar[0]
        runner_up = similar[1].score if len(similar) > 1 else 0.0
        has_context = bool(mention.hints.get("division") or mention.hints.get("event"))
        clear_winner = best.score - runner_up > 0.15

        if has_context and best.score >= CONTEXT_FLOOR and clear_winner:
            return Resolution(
                mention,
                "matched",
                best.entity_id,
                best.name,
                3,
                70,
                f"parecido {best.score:.2f} con contexto",
                similar,
            )
        return Resolution(
            mention,
            "ambiguous",
            level=4,
            confidence=int(best.score * 50),
            reason=f"parecido {best.score:.2f}, sin certeza",
            candidates=similar,
        )
