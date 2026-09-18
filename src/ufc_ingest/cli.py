"""Punto de entrada: `uv run ufc-ingest <comando>`."""

import json
import os
from pathlib import Path

import typer

from .db.connection import connect, safe_url
from .db.migrations import run as run_migrations
from .db.repositories import roles
from .pipeline import parity, publish, seed_import

app = typer.Typer(help="Pipeline de datos de UFC Graph", no_args_is_help=True)

WEB_ROLE_OPTION = typer.Option("ufc_web", "--role", help="Usuario de solo lectura de la web")
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
    done = run_migrations()
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
def set_web_password(role: str = WEB_ROLE_OPTION) -> None:
    """Fija la contraseña del usuario de solo lectura (se lee de WEB_DB_PASSWORD)."""
    password = os.environ.get("WEB_DB_PASSWORD")
    if not password:
        typer.echo("Falta WEB_DB_PASSWORD en el entorno.")
        raise typer.Exit(1)
    with connect() as conn, conn.cursor() as cur:
        roles.set_web_password(cur, role, password)
        conn.commit()
        leaks = roles.can_read_tables(cur, role)
    typer.echo(f"Contraseña fijada para {role}.")
    typer.echo(
        "✗ El usuario puede leer tablas directamente: revisa los permisos."
        if leaks
        else "✓ Sin acceso directo a tablas: solo published_graph()."
    )


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
    with connect() as conn:
        rebuilt = publish.build(conn)
    problems = parity.compare(seed, rebuilt)

    if problems:
        typer.echo(f"✗ {len(problems)} diferencias:")
        for p in problems[:25]:
            typer.echo(f"  {p}")
        raise typer.Exit(1)
    typer.echo("✓ El grafo reconstruido es idéntico al dataset semilla")


if __name__ == "__main__":
    app()
