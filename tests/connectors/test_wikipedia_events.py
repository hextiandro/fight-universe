"""El conector se prueba contra una respuesta grabada: si Wikipedia cambia, falla aquí
y no en producción. Los valores esperados son los que ya teníamos verificados."""

from pathlib import Path

import pytest

from ufc_ingest.connectors.base import RawDoc
from ufc_ingest.connectors.wikipedia_events import WikipediaEvents

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ufc_327.html"


@pytest.fixture
def candidates() -> list:
    doc = RawDoc(
        source_id="wikipedia-events",
        url="https://en.wikipedia.org/wiki/UFC_327",
        hash="fixture",
        payload={"title": "UFC 327", "html": FIXTURE.read_text()},
    )
    return list(WikipediaEvents().extract(doc))


def test_extrae_el_evento(candidates: list) -> None:
    event = next(c for c in candidates if c.kind == "event")
    assert event.payload["date"] == "2026-04-11"
    assert event.payload["venue"] == "Kaseya Center"
    assert "Miami" in event.payload["city"]


def test_extrae_la_pelea_estelar_como_la_teniamos(candidates: list) -> None:
    main = next(c for c in candidates if c.kind == "fight" and c.payload["cardPosition"] == 0)
    assert main.payload["fighters"] == ["Carlos Ulberg", "Jiří Procházka"]
    assert main.payload["winner"] == "Carlos Ulberg"
    assert main.payload["method"] == "KO/TKO"
    assert main.payload["round"] == 1
    assert main.payload["time"] == "3:45"
    assert main.payload["divisionId"] == "light-heavyweight"


def test_las_menciones_llevan_su_pagina_de_wikipedia(candidates: list) -> None:
    main = next(c for c in candidates if c.kind == "fight")
    fighters = [m for m in main.mentions if m.entity_type == "fighter"]
    assert [m.hints["wikipedia"] for m in fighters] == ["Carlos Ulberg", "Jiří Procházka"]


def test_las_decisiones_no_repiten_el_detalle(candidates: list) -> None:
    decisions = [c for c in candidates if c.kind == "fight" and c.payload["method"] in {"UD", "SD", "MD"}]
    assert decisions, "el evento tenía decisiones"
    assert all(c.payload["methodDetail"] is None for c in decisions)


def test_ignora_las_divisiones_femeninas(candidates: list) -> None:
    assert all("women" not in c.payload.get("divisionId", "") for c in candidates if c.kind == "fight")
