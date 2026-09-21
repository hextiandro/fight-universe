"""Vocabulario común: cada fuente escribe distinto, el modelo habla un solo idioma.

Los conectores usan estas funciones; no definen etiquetas propias. Es lo que evita que
Wikipedia traiga "TKO (punches)", otra fuente "Knockout" y acabemos con tres valores para
el mismo hecho.
"""

import re

from .models import FightMethod

# Solo divisiones masculinas por ahora (decisión de alcance del corte 2).
DIVISIONS: dict[str, str] = {
    "heavyweight": "heavyweight",
    "light heavyweight": "light-heavyweight",
    "middleweight": "middleweight",
    "welterweight": "welterweight",
    "lightweight": "lightweight",
    "featherweight": "featherweight",
    "bantamweight": "bantamweight",
    "flyweight": "flyweight",
    "265 lb": "heavyweight",
    "205 lb": "light-heavyweight",
    "185 lb": "middleweight",
    "170 lb": "welterweight",
    "155 lb": "lightweight",
    "145 lb": "featherweight",
    "135 lb": "bantamweight",
    "125 lb": "flyweight",
}

# El orden importa: "technical submission" antes que "submission".
METHOD_PATTERNS: list[tuple[str, FightMethod]] = [
    (r"\bno contest\b|\bnc\b", "NC"),
    (r"\bdraw\b", "DRAW"),
    (r"technical submission|submission|\bsub\b", "SUB"),
    (r"\bko\b|\btko\b|knockout|technical knockout", "KO/TKO"),
    (r"unanimous", "UD"),
    (r"split", "SD"),
    (r"majority", "MD"),
]

TRANSLATIONS = {
    "punches": "puñetazos",
    "punch": "puñetazo",
    "elbows": "codazos",
    "kick": "patada",
    "head kick": "patada a la cabeza",
    "rear-naked choke": "estrangulación por detrás",
    "guillotine choke": "guillotina",
    "armbar": "palanca de brazo",
    "triangle choke": "triángulo",
    "doctor stoppage": "parada médica",
    "corner stoppage": "parada de la esquina",
    "retirement": "abandono",
    "accidental eye poke": "piquete de ojo accidental",
    "decision": "decisión",
}


def parse_division(text: str) -> str | None:
    """ "Light Heavyweight" y "205 lb" son la misma división."""
    key = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    key = " ".join(key.replace("women's", "").split())
    if "women" in text.lower():
        return None  # fuera de alcance por ahora
    return DIVISIONS.get(key) or DIVISIONS.get(key.replace("catchweight", "").strip())


def parse_method(text: str) -> tuple[FightMethod, str | None]:
    """ "KO (punches)" → ("KO/TKO", "puñetazos"). El detalle se conserva traducido."""
    lowered = text.lower().strip()
    method: FightMethod | None = None
    for pattern, value in METHOD_PATTERNS:
        if re.search(pattern, lowered):
            method = value
            break
    if method is None:
        method = "UD" if "decision" in lowered else "KO/TKO"

    detail = None
    if match := re.search(r"\(([^)]+)\)", text):
        raw = match.group(1).strip().lower()
        # "UD (unanimous)" no aporta nada: el detalle ya está en el método.
        if raw not in {"unanimous", "split", "majority", "decision"}:
            detail = TRANSLATIONS.get(raw, raw)
    return method, detail


def parse_round(text: str) -> int | None:
    match = re.search(r"\d+", text)
    return int(match.group()) if match else None


def parse_time(text: str) -> str | None:
    match = re.search(r"\d{1,2}:\d{2}", text)
    return match.group() if match else None
