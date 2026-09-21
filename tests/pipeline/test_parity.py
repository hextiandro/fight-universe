"""La comparación de paridad debe detectar faltantes, sobrantes y diferencias."""

import json
from pathlib import Path

from ufc_ingest.pipeline import parity

SEED = {
    "fighters": [{"id": "a", "name": "A", "divisionId": "heavyweight", "image": {"src": "x"}}],
    "events": [{"id": "e1", "name": "E", "date": "2026-01-01"}],
}
# La foto forma parte del grafo publicado, así que también se compara.


def _seed_file(tmp_path: Path) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(SEED))
    return path


def test_identico_no_da_problemas(tmp_path: Path) -> None:
    rebuilt = {
        "fighters": [{"id": "a", "name": "A", "divisionId": "heavyweight", "image": {"src": "x"}}],
        "events": [{"id": "e1", "name": "E", "date": "2026-01-01"}],
    }
    assert parity.compare(_seed_file(tmp_path), rebuilt) == []


def test_detecta_faltante_sobrante_y_diferencia(tmp_path: Path) -> None:
    rebuilt = {
        "fighters": [{"id": "a", "name": "OTRO", "divisionId": "heavyweight", "image": {"src": "x"}}],
        "events": [{"id": "e2", "name": "E", "date": "2026-01-01"}],
    }
    problems = parity.compare(_seed_file(tmp_path), rebuilt)
    assert "fighters: difiere en a" in problems
    assert "events: falta e1" in problems
    # Lo que la ingestión añade no es un problema: e2 no se reporta.
    assert not any("e2" in p for p in problems)


def test_una_fuente_extra_no_es_regresion(tmp_path: Path) -> None:
    """Que otra fuente corrobore el dato es lo que buscamos, no un problema."""
    seed = {"events": [{"id": "e1", "name": "E", "provenance": {"sourceIds": ["espn"], "verified": True}}]}
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed))
    rebuilt = {
        "events": [
            {"id": "e1", "name": "E", "provenance": {"sourceIds": ["espn", "wikipedia"], "verified": True}}
        ]
    }
    assert parity.compare(path, rebuilt) == []


def test_perder_una_fuente_si_lo_es(tmp_path: Path) -> None:
    seed = {"events": [{"id": "e1", "name": "E", "provenance": {"sourceIds": ["espn"], "verified": True}}]}
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(seed))
    rebuilt = {
        "events": [{"id": "e1", "name": "E", "provenance": {"sourceIds": ["wikipedia"], "verified": False}}]
    }
    problems = parity.compare(path, rebuilt)
    assert any("pierde fuentes espn" in p for p in problems)
    assert any("deja de estar verificado" in p for p in problems)
