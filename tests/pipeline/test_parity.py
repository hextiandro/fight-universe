"""La comparación de paridad debe detectar faltantes, sobrantes y diferencias."""

import json
from pathlib import Path

from ufc_ingest.pipeline import parity

SEED = {
    "fighters": [{"id": "a", "name": "A", "divisionId": "heavyweight", "image": {"src": "x"}}],
    "events": [{"id": "e1", "name": "E", "date": "2026-01-01"}],
}


def _seed_file(tmp_path: Path) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(SEED))
    return path


def test_identico_no_da_problemas(tmp_path: Path) -> None:
    rebuilt = {
        "fighters": [{"id": "a", "name": "A", "divisionId": "heavyweight"}],
        "events": [{"id": "e1", "name": "E", "date": "2026-01-01"}],
    }
    assert parity.compare(_seed_file(tmp_path), rebuilt) == []


def test_detecta_faltante_sobrante_y_diferencia(tmp_path: Path) -> None:
    rebuilt = {
        "fighters": [{"id": "a", "name": "OTRO", "divisionId": "heavyweight"}],
        "events": [{"id": "e2", "name": "E", "date": "2026-01-01"}],
    }
    problems = parity.compare(_seed_file(tmp_path), rebuilt)
    assert "fighters: difiere a" in problems
    assert "events: sobra e2" in problems
    assert "events: falta e1" in problems
