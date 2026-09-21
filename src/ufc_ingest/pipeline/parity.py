"""Caso de uso: comprobar que el dataset semilla sigue intacto en el grafo.

Nació para verificar la migración a Postgres (debía salir idéntico). Ahora que la
ingestión añade datos nuevos, comprueba lo que sigue importando: que nada de lo sembrado
se haya perdido ni alterado. Lo que sobra es dato nuevo, y es bienvenido.
"""

import json
from pathlib import Path
from typing import Any


def compare(seed_path: Path, rebuilt: dict[str, Any]) -> list[str]:
    original = json.loads(seed_path.read_text())
    problems: list[str] = []

    for key, rebuilt_items in rebuilt.items():
        pending = {item["id"]: item for item in original[key]}

        for item in rebuilt_items:
            expected = pending.pop(item["id"], None)
            if expected is None:
                continue  # dato nuevo traído por la ingestión
            problems.extend(f"{key}: {d} en {item['id']}" for d in _differences(expected, item))
        problems.extend(f"{key}: falta {missing}" for missing in pending)

    return problems


def _differences(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Los valores deben coincidir; las fuentes pueden haber aumentado.

    Que otra fuente corrobore un dato no es una regresión: es justo lo que buscamos.
    Lo que no puede pasar es que se pierda una fuente o que cambie un valor.
    """
    problems = []
    if _canonical(_without_provenance(expected)) != _canonical(_without_provenance(actual)):
        problems.append("difiere")

    seed_sources = expected.get("provenance", {}).get("sourceIds", [])
    now_sources = actual.get("provenance", {}).get("sourceIds", [])
    if lost := [s for s in seed_sources if s not in now_sources]:
        problems.append(f"pierde fuentes {', '.join(lost)}")
    if expected.get("provenance", {}).get("verified") and not actual.get("provenance", {}).get("verified"):
        problems.append("deja de estar verificado")
    return problems


def _without_provenance(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k != "provenance"}


def _canonical(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=False)
