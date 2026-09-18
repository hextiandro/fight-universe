"""Acceso a Postgres. SQL plano con psycopg 3: el esquema manda, sin ORM de por medio."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from ..config import settings


@contextmanager
def connect(autocommit: bool = False) -> Iterator[psycopg.Connection]:
    with psycopg.connect(settings.database_url, row_factory=dict_row, autocommit=autocommit) as conn:
        yield conn


def safe_url() -> str:
    """La cadena de conexión sin credenciales, para poder registrarla en los logs."""
    info = psycopg.conninfo.conninfo_to_dict(settings.database_url)
    return f"{info.get('host', '?')}:{info.get('port', '?')}/{info.get('dbname', '?')}"
