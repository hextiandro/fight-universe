"""Puerto de entrada: el contrato que cumple toda fuente de datos.

El núcleo no sabe si detrás hay Wikipedia, un feed RSS o un proveedor de pago. Añadir una
fuente es añadir un adaptador en esta carpeta; nada más cambia.
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol

from pydantic import BaseModel, Field

from ..domain.models import EntityType


class RawDoc(BaseModel):
    """Respuesta íntegra de la fuente. El hash evita reprocesar lo mismo dos veces."""

    source_id: str
    url: str | None = None
    hash: str
    payload: dict[str, Any]
    fetched_at: datetime | None = None


class Mention(BaseModel):
    """Una entidad tal y como la nombra la fuente, todavía sin resolver.

    "Ilia", "Ilia Topuria" y "Topuria" son tres menciones de la misma entidad; resolverlas
    es trabajo de `resolution`, no del conector.
    """

    entity_type: EntityType
    text: str
    # Pistas que ayudan a desambiguar: id externo, división, rival, fecha…
    hints: dict[str, Any] = Field(default_factory=dict)


class Candidate(BaseModel):
    """Un hecho propuesto por un conector, pendiente de resolver y (si hace falta) revisar."""

    kind: str  # 'event', 'fight', 'development'…
    payload: dict[str, Any]
    mentions: list[Mention] = Field(default_factory=list)
    source_id: str
    raw_doc_hash: str
    confidence: int = 50


class Connector(Protocol):
    """Todo conector hace dos cosas y nada más: traer documentos y proponer hechos."""

    id: str
    trust: int

    def fetch(self, since: datetime | None = None) -> Iterable[RawDoc]: ...

    def extract(self, doc: RawDoc) -> Iterable[Candidate]: ...
