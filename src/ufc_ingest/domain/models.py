"""El modelo de dominio: entidades y hechos, sin SQL ni HTTP.

Regla de dependencias: `domain` no importa nada de `db`, `connectors` ni `pipeline`.
Los adaptadores dependen del dominio, nunca al revés.
"""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

EntityType = Literal["fighter", "event", "division", "fight", "development"]
FightMethod = Literal["KO/TKO", "SUB", "UD", "SD", "MD", "NC", "DRAW"]
TitleStakes = Literal["undisputed", "vacant-undisputed", "interim"]
DevelopmentKind = Literal[
    "title-vacated", "title-awarded", "ranking-change", "statement", "fight-expected", "injury"
]
# Certeza del hecho, no de la fuente.
DevelopmentStatus = Literal["official", "confirmed", "statement", "reported", "rumor"]
SourceType = Literal["official", "media", "reference", "stats", "manual"]


class Source(BaseModel):
    id: str
    name: str
    url: str | None = None
    type: SourceType
    retrieved_at: date | None = None


class Provenance(BaseModel):
    """De dónde sale un dato. El orden de las fuentes importa: la primera es la principal."""

    source_ids: list[str] = Field(default_factory=list)
    verified: bool = False
    note: str | None = None


class Claim(BaseModel):
    """Un valor con su respaldo. La entidad guarda lo vigente; el claim, por qué lo creemos."""

    subject_type: EntityType
    subject_id: str
    field: str
    value: Any
    provenance: Provenance
    valid_from: date | None = None


class Division(BaseModel):
    id: str
    name: str
    limit_lb: int
    order: int


class Fighter(BaseModel):
    id: str
    slug: str
    name: str
    nationality: str | None = None
    division_id: str
    aliases: list[str] = Field(default_factory=list)


class Event(BaseModel):
    id: str
    slug: str
    name: str
    date: date
    venue: str | None = None
    city: str | None = None


class Fight(BaseModel):
    id: str
    slug: str
    event_id: str
    date: date
    division_id: str
    fighter_ids: list[str]
    winner_id: str | None = None
    method: FightMethod
    method_detail: str | None = None
    round: int | None = None
    time: str | None = None
    title: TitleStakes | None = None


class EntityRef(BaseModel):
    type: EntityType
    id: str


class TitleChange(BaseModel):
    division_id: str
    stakes: Literal["undisputed", "interim"]
    holder_id: str | None = None


class Development(BaseModel):
    id: str
    slug: str
    kind: DevelopmentKind
    status: DevelopmentStatus
    date: date
    title: str
    summary: str
    about: list[EntityRef] = Field(default_factory=list)
    title_change: TitleChange | None = None
