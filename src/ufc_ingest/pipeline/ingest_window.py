"""Caso de uso: ingerir toda la ventana de eventos de una fuente."""

import time
from collections.abc import Callable

import psycopg

from ..connectors.wikipedia_events import WikipediaEvents
from . import ingest_event

# Wikimedia pide peticiones en serie y con pausa. La carga manual pasaba desapercibida,
# pero un cron diario desde las IPs compartidas de GitHub sí acumula: sin esto nos
# arriesgamos a un bloqueo que dejaría el grafo congelado sin avisar.
COURTESY_DELAY_S = 1.0


def run(
    conn: psycopg.Connection,
    months: int = 6,
    on_event: Callable[[str, ingest_event.IngestReport], None] | None = None,
    delay: float = COURTESY_DELAY_S,
) -> dict[str, int]:
    events = WikipediaEvents().window(months=months)
    totals = {"eventos": 0, "aplicados": 0, "a revisión": 0, "sin cambios": 0, "fallidos": 0}

    for position, event in enumerate(events):
        if position and delay:
            time.sleep(delay)
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
