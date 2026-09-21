"""Quien revisa tiene que poder decidir en segundos: el resumen debe decir qué es,
de dónde sale y por qué no entró solo."""

from ufc_ingest.pipeline import review


def test_describe_alta_de_peleador() -> None:
    item = {
        "candidate": {
            "kind": "fighter",
            "name": "Paulo Costa",
            "hints": {"division": "light-heavyweight", "wikipedia": "Paulo Costa"},
        },
        "reason": "alta de peleador",
        "confidence": 0,
    }
    text = "\n".join(review.describe(item))
    assert "Paulo Costa" in text
    assert "light-heavyweight" in text
    assert "alta de peleador" in text


def test_describe_propone_el_parecido_encontrado() -> None:
    item = {
        "candidate": {
            "kind": "fighter",
            "name": "Alexander Volkanovsky",
            "hints": {},
            "proposal": {"name": "Alexander Volkanovski", "level": 3},
            "candidates": [{"name": "Alexander Volkanovski", "score": 0.83}],
        },
        "reason": "parecido 0.83",
        "confidence": 41,
    }
    text = "\n".join(review.describe(item))
    assert "¿es el mismo que «Alexander Volkanovski»?" in text
    assert "0.83" in text


def test_describe_pelea() -> None:
    item = {
        "candidate": {
            "kind": "fight",
            "fighters": ["Paulo Costa", "Azamat Murzakanov"],
            "divisionId": "light-heavyweight",
            "method": "KO/TKO",
            "methodDetail": "patada a la cabeza",
            "round": 3,
            "time": "1:23",
            "winner": "Paulo Costa",
        },
        "reason": "peleadores pendientes",
        "confidence": 60,
    }
    text = "\n".join(review.describe(item))
    assert "Paulo Costa vs Azamat Murzakanov" in text
    assert "gana Paulo Costa" in text
    assert "R3" in text
