"""Las reglas de dependencia se comprueban, no se confía en la buena voluntad."""

from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "ufc_ingest"


def _files(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


@pytest.mark.parametrize("path", _files("domain"), ids=lambda p: p.name)
def test_el_dominio_no_depende_de_la_infraestructura(path: Path) -> None:
    code = path.read_text()
    for forbidden in ["psycopg", "httpx", "from ..db", "from ..connectors", "from ..pipeline"]:
        assert forbidden not in code, f"el dominio no debe depender de {forbidden}"


@pytest.mark.parametrize(
    "path",
    _files("domain") + _files("pipeline") + _files("connectors") + _files("resolution"),
    ids=lambda p: p.name,
)
def test_el_sql_vive_solo_en_db(path: Path) -> None:
    code = path.read_text().lower()
    for statement in ["insert into", "select ", "update ", "delete from"]:
        assert statement not in code, f"contiene SQL; debe ir en db/repositories ({statement})"


@pytest.mark.parametrize("path", _files("domain") + _files("pipeline") + _files("db"), ids=lambda p: p.name)
def test_las_peticiones_http_viven_solo_en_connectors(path: Path) -> None:
    assert "httpx" not in path.read_text(), "las llamadas a fuentes externas van en connectors/"
