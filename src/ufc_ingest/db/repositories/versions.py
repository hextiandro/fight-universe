"""Versiones publicadas: permiten reproducir después cualquier pieza ya difundida."""

import json
from typing import Any

import psycopg


def save(cur: psycopg.Cursor, published: dict[str, Any]) -> int:
    counts = {key: len(value) for key, value in published.items()}
    cur.execute(
        "insert into published_versions (counts, payload) values (%s, %s) returning id",
        (json.dumps(counts), json.dumps(published, ensure_ascii=False, sort_keys=True)),
    )
    return cur.fetchone()["id"]
