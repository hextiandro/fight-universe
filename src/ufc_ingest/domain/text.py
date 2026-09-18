"""Normalización de texto compartida por la resolución de entidades y la búsqueda."""

import unicodedata


def normalize(text: str) -> str:
    """Igual que la normalización de la web: minúsculas, sin acentos ni puntuación."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    stripped = "".join(c for c in decomposed if unicodedata.category(c) != "Mn")
    cleaned = "".join(c if c.isalnum() else " " for c in stripped)
    return " ".join(cleaned.split())
