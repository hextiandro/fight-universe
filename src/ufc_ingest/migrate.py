"""Aplicador de migraciones: archivos SQL numerados en `schema/`, aplicados una sola vez.

Sin herramienta externa a propósito: son archivos SQL planos, así que sirven igual para
Postgres local, para Supabase o para cualquier otro proveedor.
"""

import hashlib
from pathlib import Path

from .config import settings
from .db import connect

TRACKING_TABLE = """
create table if not exists schema_migrations (
  version     text primary key,
  checksum    text not null,
  applied_at  timestamptz not null default now()
)
"""


def pending(applied: dict[str, str]) -> list[Path]:
    files = sorted(settings.schema_dir.glob("*.sql"))
    result = []
    for path in files:
        version = path.stem
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if version not in applied:
            result.append(path)
        elif applied[version] != checksum:
            raise RuntimeError(
                f"La migración {version} cambió después de aplicarse. "
                "Crea una migración nueva en vez de editar una ya aplicada."
            )
    return result


def run() -> list[str]:
    """Aplica lo que falte y devuelve las versiones aplicadas en esta ejecución."""
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(TRACKING_TABLE)
            cur.execute("select version, checksum from schema_migrations")
            applied = {row["version"]: row["checksum"] for row in cur.fetchall()}
        conn.commit()

        done = []
        for path in pending(applied):
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
            with conn.cursor() as cur:
                cur.execute(path.read_text())
                cur.execute(
                    "insert into schema_migrations (version, checksum) values (%s, %s)",
                    (path.stem, checksum),
                )
            conn.commit()
            done.append(path.stem)
        return done
