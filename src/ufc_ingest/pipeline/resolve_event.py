"""Caso de uso: leer un evento de una fuente y resolver sus menciones.

Todavía no escribe en la base de datos: muestra qué se resolvió, con qué nivel y qué
queda dudoso. Sirve para medir la calidad de la resolución antes de dejarla escribir.
"""

from dataclasses import dataclass

import psycopg

from ..connectors.wikipedia_events import WikipediaEvents
from ..db.repositories.lookup import DbLookup
from ..resolution.resolver import EntityResolver, Resolution


@dataclass
class EventResolution:
    event: dict
    resolutions: list[Resolution]

    @property
    def summary(self) -> dict[str, int]:
        counts = {"automático": 0, "a revisión": 0, "desconocido": 0}
        for r in self.resolutions:
            if r.status == "unknown":
                counts["desconocido"] += 1
            elif r.needs_review:
                counts["a revisión"] += 1
            else:
                counts["automático"] += 1
        return counts


def run(event_title: str, conn: psycopg.Connection) -> EventResolution:
    connector = WikipediaEvents()
    doc = connector.fetch_page(event_title)
    candidates = list(connector.extract(doc))
    event = next((c.payload for c in candidates if c.kind == "event"), {})

    # Una mención por entidad distinta: el mismo peleador aparece en varias filas.
    seen: dict[tuple[str, str], object] = {}
    for candidate in candidates:
        for mention in candidate.mentions:
            seen.setdefault((mention.entity_type, mention.text), mention)

    with conn.cursor() as cur:
        resolver = EntityResolver(DbLookup(cur))
        resolutions = [resolver.resolve(m) for m in seen.values()]  # type: ignore[arg-type]

    return EventResolution(event=event, resolutions=resolutions)
