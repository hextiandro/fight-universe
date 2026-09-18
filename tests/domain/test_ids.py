"""Los identificadores deben ser estables: el grafo de mañana conserva las entidades de hoy."""

import pytest

from ufc_ingest.domain.ids import make_id
from ufc_ingest.domain.text import normalize


def test_id_estable_entre_ejecuciones() -> None:
    assert make_id("fighter", "ilia-topuria") == make_id("fighter", "ilia-topuria")


def test_id_opaco_y_con_prefijo() -> None:
    fid = make_id("fighter", "ilia-topuria")
    assert fid.startswith("f_") and len(fid) == 14
    assert "topuria" not in fid, "el id no debe derivarse del nombre"


def test_entidades_distintas_no_colisionan() -> None:
    ids = {
        make_id("fighter", "jose-delgado"),
        make_id("fighter", "jose-delgado-2"),
        make_id("event", "jose-delgado"),
    }
    assert len(ids) == 3


def test_tipo_desconocido() -> None:
    with pytest.raises(ValueError):
        make_id("gimnasio", "fighting-nerds")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("Jiří Procházka", "jiri prochazka"),
        ("Khalil Rountree Jr.", "khalil rountree jr"),
        ("  ILIA   TOPURIA ", "ilia topuria"),
        ("José Delgado", "jose delgado"),
    ],
)
def test_normalizacion(texto: str, esperado: str) -> None:
    assert normalize(texto) == esperado
