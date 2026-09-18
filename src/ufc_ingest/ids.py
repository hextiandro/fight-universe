"""Identificadores internos estables.

El id no se deriva del nombre: dos homónimos ("José Delgado") chocarían. Se deriva de un
slug, que sí puede cambiar sin romper nada, porque el id ya está fijado. Es determinista,
así que reimportar la misma semilla produce los mismos ids.
"""

import hashlib

PREFIXES = {
    "fighter": "f",
    "event": "e",
    "fight": "b",  # bout
    "development": "d",
    "division": "v",
    "source": "s",
}

_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"  # base32 sin i, l, o, u


def _encode(digest: bytes, length: int) -> str:
    number = int.from_bytes(digest, "big")
    out = []
    for _ in range(length):
        number, rest = divmod(number, len(_ALPHABET))
        out.append(_ALPHABET[rest])
    return "".join(reversed(out))


def make_id(kind: str, seed: str, length: int = 12) -> str:
    """Id opaco y determinista: `f_9x2k4m8qz1v7`."""
    if kind not in PREFIXES:
        raise ValueError(f"tipo de entidad desconocido: {kind}")
    digest = hashlib.sha256(f"{kind}:{seed}".encode()).digest()
    return f"{PREFIXES[kind]}_{_encode(digest, length)}"


def normalize(text: str) -> str:
    """Igual que la normalización de la web: minúsculas, sin acentos ni puntuación."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    cleaned = "".join(c if c.isalnum() else " " for c in stripped)
    return " ".join(cleaned.split())
