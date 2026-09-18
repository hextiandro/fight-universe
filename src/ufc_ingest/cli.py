"""Punto de entrada: `uv run ufc-ingest <comando>`."""

import typer

from . import migrate
from .db import connect, safe_url

app = typer.Typer(help="Pipeline de datos de UFC Graph", no_args_is_help=True)


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
    tables = ["divisions", "fighters", "events", "fights", "developments", "claims", "review_queue"]
    with connect() as conn, conn.cursor() as cur:
        for table in tables:
            cur.execute(f"select count(*) as n from {table}")  # noqa: S608 - lista fija
            typer.echo(f"  {table:<16} {cur.fetchone()['n']}")


if __name__ == "__main__":
    app()
