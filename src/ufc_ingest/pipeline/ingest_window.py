"""Caso de uso: ingerir toda la ventana de eventos de una fuente."""

from collections.abc import Callable

import psycopg

from ..connectors.wikipedia_events import WikipediaEvents
from . import ingest_event


def run(
    conn: psycopg.Connection,
    months: int = 6,
    on_event: Callable[[str, ingest_event.IngestReport], None] | None = None,
) -> dict[str, int]:
    events = WikipediaEvents().window(months=months)
    totals = {"eventos": 0, "aplicados": 0, "a revisión": 0, "sin cambios": 0, "fallidos": 0}

    for event in events:
        try:
            report = ingest_event.run(event["title"], conn)
        except Exception as error:  # una página rara no debe detener la carga entera
            totals["fallidos"] += 1
            if on_event:
                on_event(event["title"], ingest_event.IngestReport(event=str(error)))
            continue
        totals["eventos"] += 1
        totals["aplicados"] += len(report.applied)
        totals["a revisión"] += len(report.queued)
        totals["sin cambios"] += len(report.skipped)
        if on_event:
            on_event(event["title"], report)
    return totals
