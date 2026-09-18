"""Caso de uso: comprobar que el grafo reconstruido es idéntico al dataset semilla.

Es la prueba de que la migración no perdió nada. Sin esto, "funciona" solo significa
"no dio error".
"""

import json
from pathlib import Path
from typing import Any


def compare(seed_path: Path, rebuilt: dict[str, Any]) -> list[str]:
    original = json.loads(seed_path.read_text())
    problems: list[str] = []

    for key, rebuilt_items in rebuilt.items():
        source_items = original[key]
        if key == "fighters":  # la semilla trae la imagen aparte; se compara sin ella
            source_items = [{k: v for k, v in f.items() if k != "image"} for f in source_items]
        pending = {item["id"]: item for item in source_items}

        for item in rebuilt_items:
            expected = pending.pop(item["id"], None)
            if expected is None:
                problems.append(f"{key}: sobra {item['id']}")
            elif _canonical(expected) != _canonical(item):
                problems.append(f"{key}: difiere {item['id']}")
        problems.extend(f"{key}: falta {missing}" for missing in pending)

    return problems


def _canonical(item: dict[str, Any]) -> str:
    return json.dumps(item, sort_keys=True, ensure_ascii=False)
