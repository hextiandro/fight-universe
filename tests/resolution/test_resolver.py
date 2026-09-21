"""El resolutor decide sin base de datos: se prueba con un catálogo falso."""

import pytest

from ufc_ingest.connectors.base import Mention
from ufc_ingest.resolution.resolver import EntityResolver, Match


class FakeLookup:
    def __init__(self, external=None, by_name=None, similar=None) -> None:
        self._external = external or {}
        self._by_name = by_name or {}
        self._similar = similar or []

    def by_external_id(self, entity_type, system, value):
        return self._external.get((system, value))

    def by_name(self, entity_type, normalized):
        return self._by_name.get(normalized, [])

    def similar(self, entity_type, normalized, limit=5):
        return self._similar


def mention(text: str, **hints) -> Mention:
    return Mention(entity_type="fighter", text=text, hints=hints)


def test_nivel_1_id_externo_gana_a_todo() -> None:
    lookup = FakeLookup(external={("wikipedia", "Ilia Topuria"): Match("f_1", "Ilia Topuria", 1.0)})
    result = EntityResolver(lookup).resolve(mention("Topuria", wikipedia="Ilia Topuria"))
    assert (result.status, result.level, result.entity_id) == ("matched", 1, "f_1")
    assert not result.needs_review


def test_nivel_2_nombre_normalizado_sin_acentos() -> None:
    lookup = FakeLookup(by_name={"jiri prochazka": [Match("f_2", "Jiří Procházka", 1.0)]})
    result = EntityResolver(lookup).resolve(mention("Jiří Procházka"))
    assert (result.status, result.level) == ("matched", 2)
    assert not result.needs_review


def test_homonimos_van_a_revision() -> None:
    lookup = FakeLookup(
        by_name={"jose delgado": [Match("f_3", "José Delgado", 1.0), Match("f_4", "José Delgado", 1.0)]}
    )
    result = EntityResolver(lookup).resolve(mention("José Delgado"))
    assert result.status == "ambiguous"
    assert result.needs_review
    assert len(result.candidates) == 2


def test_nivel_3_parecido_con_contexto_se_propone_pero_se_revisa() -> None:
    lookup = FakeLookup(similar=[Match("f_5", "Ilia Topuria", 0.78), Match("f_6", "Ilia Toporia", 0.4)])
    result = EntityResolver(lookup).resolve(mention("Ilya Topuriya", division="lightweight"))
    assert (result.status, result.level) == ("matched", 3)
    assert result.needs_review, "el parecido nunca entra solo"


def test_parecido_sin_contexto_no_decide() -> None:
    lookup = FakeLookup(similar=[Match("f_5", "Ilia Topuria", 0.78)])
    result = EntityResolver(lookup).resolve(mention("Ilya Topuriya"))
    assert result.status == "ambiguous"


def test_dos_candidatos_parecidos_no_deciden() -> None:
    lookup = FakeLookup(
        similar=[Match("f_7", "Umar Nurmagomedov", 0.82), Match("f_8", "Usman Nurmagomedov", 0.8)]
    )
    result = EntityResolver(lookup).resolve(mention("Nurmagomedov", division="bantamweight"))
    assert result.status == "ambiguous", "dos hermanos no se distinguen por parecido"


def test_desconocido_cuando_no_hay_nada() -> None:
    result = EntityResolver(FakeLookup()).resolve(mention("Peleador Nuevo"))
    assert (result.status, result.confidence) == ("unknown", 0)


@pytest.mark.parametrize("texto", ["Ilia Topuria", "ILIA  TOPURIA", "Ilia Topuria "])
def test_el_nombre_se_normaliza_igual(texto: str) -> None:
    lookup = FakeLookup(by_name={"ilia topuria": [Match("f_1", "Ilia Topuria", 1.0)]})
    assert EntityResolver(lookup).resolve(mention(texto)).entity_id == "f_1"
