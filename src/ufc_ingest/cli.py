"""Punto de entrada: `uv run ufc-ingest <comando>`."""

import json
from pathlib import Path

import typer

from . import migrate, publish, seed_import
from .db import connect, safe_url

app = typer.Typer(help="Pipeline de datos de UFC Graph", no_args_is_help=True)

SEED_OPTION = typer.Option(..., "--from", help="Ruta a seed.json exportado por la web")
OUT_OPTION = typer.Option(None, "--out", help="Escribe el grafo publicado en un archivo")
TABLES = [
    "divisions",
    "sources",
    "fighters",
    "events",
    "fights",
    "developments",
    "claims",
    "review_queue",
]


@app.command()
def migrate_db() -> None:
    """Aplica las migraciones pendientes de `schema/`."""
    typer.echo(f"Base de datos: {safe_url()}")
    done = migrate.run()
    typer.echo("Sin migraciones pendientes." if not done else f"Aplicadas: {', '.join(done)}")


@app.command()
def status() -> None:
    """Resumen de lo que hay en la base de datos."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn, conn.cursor() as cur:
        for table in TABLES:
            cur.execute(f"select count(*) as n from {table}")  # noqa: S608 - lista fija
            typer.echo(f"  {table:<16} {cur.fetchone()['n']}")


@app.command()
def import_seed(seed: Path = SEED_OPTION) -> None:
    """Importa el dataset semilla al modelo canónico (idempotente)."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn:
        counts = seed_import.run(seed, conn)
    typer.echo("Importado: " + " · ".join(f"{k}: {v}" for k, v in counts.items()))


@app.command()
def publish_graph(out: Path = OUT_OPTION) -> None:
    """Reconstruye el grafo publicado desde la base de datos."""
    with connect() as conn:
        graph = publish.build(conn)
    text = json.dumps(graph, ensure_ascii=False, indent=2, sort_keys=True)
    if out:
        out.write_text(text + "\n")
        typer.echo(f"{out} · " + " · ".join(f"{k}: {len(v)}" for k, v in graph.items()))
    else:
        typer.echo(text)


@app.command()
def verify_parity(seed: Path = SEED_OPTION) -> None:
    """Comprueba que el grafo reconstruido es idéntico al dataset semilla."""
    original = json.loads(seed.read_text())
    with connect() as conn:
        rebuilt = publish.build(conn)

    problems: list[str] = []
    for key, rebuilt_items in rebuilt.items():
        source_items = original[key]
        if key == "fighters":  # la semilla trae la imagen aparte; se compara sin ella
            source_items = [{k: v for k, v in f.items() if k != "image"} for f in source_items]
        by_id = {item["id"]: item for item in source_items}
        for item in rebuilt_items:
            expected = by_id.pop(item["id"], None)
            if expected is None:
                problems.append(f"{key}: sobra {item['id']}")
            elif json.dumps(expected, sort_keys=True, ensure_ascii=False) != json.dumps(
                item, sort_keys=True, ensure_ascii=False
            ):
                problems.append(f"{key}: difiere {item['id']}")
        problems.extend(f"{key}: falta {missing}" for missing in by_id)

    if problems:
        typer.echo(f"✗ {len(problems)} diferencias:")
        for p in problems[:25]:
            typer.echo(f"  {p}")
        raise typer.Exit(1)
    typer.echo("✓ El grafo reconstruido es idéntico al dataset semilla")


if __name__ == "__main__":
    app()
