"""Repositorio de lectura del grafo publicado.

La forma la define la función SQL `published_graph()`, no este archivo: así la web y el
pipeline consumen exactamente lo mismo y no pueden divergir.
"""

from typing import Any

import psycopg


def build(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute("select published_graph() as graph")
        return cur.fetchone()["graph"]
