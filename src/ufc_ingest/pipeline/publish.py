"""Caso de uso: construir el grafo publicado y guardar la versión."""

from typing import Any

import psycopg

from ..db.repositories import graph, versions


def build(conn: psycopg.Connection) -> dict[str, Any]:
    return graph.build(conn)


def record_version(conn: psycopg.Connection, published: dict[str, Any]) -> int:
    with conn.cursor() as cur:
        version_id = versions.save(cur, published)
    conn.commit()
    return version_id
