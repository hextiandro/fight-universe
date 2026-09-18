"""El dominio valida lo que entra: un método o un estado inventado no pasan."""

import pytest
from pydantic import ValidationError

from ufc_ingest.domain.models import Claim, Development, Fight, Provenance


def test_metodo_invalido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        Fight(
            id="b_1",
            slug="x",
            event_id="e_1",
            date="2026-06-14",
            division_id="heavyweight",
            fighter_ids=["f_1", "f_2"],
            method="RENDICION",
        )


def test_estado_de_novedad_invalido_se_rechaza() -> None:
    with pytest.raises(ValidationError):
        Development(
            id="d_1",
            slug="x",
            kind="statement",
            status="quizas",
            date="2026-06-14",
            title="t",
            summary="s",
        )


def test_procedencia_por_defecto_no_verificada() -> None:
    claim = Claim(
        subject_type="fighter",
        subject_id="f_1",
        field="record",
        value="28-4-0",
        provenance=Provenance(),
    )
    assert claim.provenance.verified is False
    assert claim.provenance.source_ids == []
