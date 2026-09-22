"""La ventana se ingiere en serie, con pausa y sin que un evento roto pare la carga."""

from unittest.mock import patch

from ufc_ingest.pipeline import ingest_event, ingest_window


class FakeWindow:
    def __init__(self, titles: list[str]) -> None:
        self._titles = titles

    def window(self, months: int = 6) -> list[dict[str, str]]:
        return [{"title": t, "date": "2026-04-11"} for t in self._titles]


def test_pauses_between_events_but_not_before_the_first() -> None:
    slept: list[float] = []
    with (
        patch.object(ingest_window, "WikipediaEvents", lambda: FakeWindow(["A", "B", "C"])),
        patch.object(ingest_window.time, "sleep", slept.append),
        patch.object(ingest_event, "run", return_value=ingest_event.IngestReport(event="ok")),
    ):
        totals = ingest_window.run(conn=None, delay=1.0)  # type: ignore[arg-type]

    assert totals["eventos"] == 3
    # Tres eventos, dos pausas: la primera petición no espera.
    assert slept == [1.0, 1.0]


def test_a_broken_page_does_not_stop_the_rest() -> None:
    def explode_on_b(title: str, conn: object) -> ingest_event.IngestReport:
        if title == "B":
            raise ValueError("página rara")
        return ingest_event.IngestReport(event="ok")

    with (
        patch.object(ingest_window, "WikipediaEvents", lambda: FakeWindow(["A", "B", "C"])),
        patch.object(ingest_window.time, "sleep", lambda _: None),
        patch.object(ingest_event, "run", explode_on_b),
    ):
        totals = ingest_window.run(conn=None)  # type: ignore[arg-type]

    assert totals["eventos"] == 2
    assert totals["fallidos"] == 1
