"""Punto de entrada: `uv run ufc-ingest <comando>`."""

import json
import os
from pathlib import Path

import typer

from .connectors.wikipedia_events import WikipediaEvents
from .db.connection import connect, safe_url
from .db.migrations import run as run_migrations
from .db.repositories import review as review_repo
from .db.repositories import roles
from .pipeline import (
    ingest_event,
    ingest_window,
    materialize,
    parity,
    publish,
    resolve_event,
    seed_import,
)
from .pipeline import review as review_flow

app = typer.Typer(help="Pipeline de datos de UFC Graph", no_args_is_help=True)

BULK_ACTOR_OPTION = typer.Option(
    "human:bulk", "--actor", help="Queda en el registro: distingue lo aprobado en bloque"
)
ACTOR_OPTION = typer.Option("human", "--actor", help="Quién revisa (queda en el registro)")
EVENT_OPTION = typer.Option(..., "--event", help='Título en Wikipedia, p. ej. "UFC 327"')
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
def probe(event: str = EVENT_OPTION) -> None:
    """Lee un evento de Wikipedia y muestra lo que entiende, sin tocar la base de datos."""
    connector = WikipediaEvents()
    doc = connector.fetch_page(event)
    typer.echo(f"Documento: {doc.url} · hash {doc.hash[:8]}")

    candidates = list(connector.extract(doc))
    for candidate in candidates:
        if candidate.kind == "event":
            p = candidate.payload
            typer.echo(f"\nEVENTO  {p['name']} · {p['date']} · {p.get('venue')} · {p.get('city')}")
            continue
        p = candidate.payload
        detail = f" ({p['methodDetail']})" if p.get("methodDetail") else ""
        result = f"gana {p['winner']}" if p.get("winner") else "sin resultado"
        typer.echo(
            f"\n{p['cardPosition'] + 1:>2}. {p['fighters'][0]} vs {p['fighters'][1]} · {p['divisionId']}"
            f"\n    {p['method']}{detail} · R{p.get('round')} · {p.get('time')} · {result}"
        )
        for mention in candidate.mentions:
            if mention.entity_type == "fighter":
                typer.echo(f"    mención: «{mention.text}» → wikipedia: {mention.hints.get('wikipedia')}")

    typer.echo(f"\n{len(candidates)} candidatos")


@app.command()
def resolve(event: str = EVENT_OPTION) -> None:
    """Resuelve las menciones de un evento contra el catálogo, sin escribir nada."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn:
        result = resolve_event.run(event, conn)

    typer.echo(f"\nEVENTO  {result.event.get('name')} · {result.event.get('date')}\n")
    for r in sorted(result.resolutions, key=lambda r: (r.level or 9, r.mention.text)):
        if r.status == "matched" and not r.needs_review:
            mark, detail = "✓", f"→ {r.name} · nivel {r.level} · {r.reason}"
        elif r.status == "matched":
            mark, detail = "?", f"→ {r.name} (a revisión) · nivel {r.level} · {r.reason}"
        elif r.status == "ambiguous":
            options = ", ".join(f"{c.name} ({c.score:.2f})" for c in r.candidates[:3])
            mark, detail = "?", f"ambiguo · {r.reason} · candidatos: {options}"
        else:
            mark, detail = "+", "no está en el catálogo: alta pendiente de aprobación"
        typer.echo(f"  {mark} «{r.mention.text}» {detail}")

    typer.echo("\n" + " · ".join(f"{k}: {v}" for k, v in result.summary.items()))


@app.command()
def ingest(event: str = EVENT_OPTION) -> None:
    """Ingiere un evento: aplica lo seguro y encola lo dudoso."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn:
        report = ingest_event.run(event, conn)
    for item in report.applied:
        typer.echo(f"  ✓ {item}")
    for item in report.queued:
        typer.echo(f"  ? {item}")
    typer.echo(f"\n{report.line()}")


@app.command()
def ingest_all(months: int = 6) -> None:
    """Ingiere todos los eventos de la ventana (por defecto, 6 meses y los anunciados)."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn:
        totals = ingest_window.run(
            conn,
            months=months,
            on_event=lambda title, report: typer.echo(f"  {title}: {report.line()}"),
        )
    typer.echo("\n" + " · ".join(f"{k}: {v}" for k, v in totals.items()))


@app.command()
def refresh_values() -> None:
    """Recalcula el valor vigente de cada entidad según la confianza de sus fuentes."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn:
        counts = materialize.run(conn)
    typer.echo(" · ".join(f"{k}: {v}" for k, v in counts.items()))


@app.command()
def bulk_approve(actor: str = BULK_ACTOR_OPTION) -> None:
    """Carga inicial: aprueba en bloque las altas de peleador sin ambigüedad."""
    typer.echo(f"Base de datos: {safe_url()}")
    with connect() as conn, conn.cursor() as cur:
        items = review_repo.pending(cur, limit=5000)
        approved = review_flow.bulk_approve_new_fighters(cur, items, actor)
        conn.commit()
        remaining = len(review_repo.pending(cur, limit=5000))
    typer.echo(f"Aprobados en bloque: {len(approved)} · quedan para revisar: {remaining}")


@app.command()
def review(actor: str = ACTOR_OPTION, limit: int = 50) -> None:
    """Revisa lo pendiente: [a] aprobar · [r] rechazar · [s] saltar · [q] salir."""
    with connect() as conn, conn.cursor() as cur:
        items = review_repo.pending(cur, limit)
        if not items:
            typer.echo("No hay nada pendiente.")
            return

        for index, item in enumerate(items, start=1):
            typer.echo(f"\n─── {index} de {len(items)} " + "─" * 40)
            for line in review_flow.describe(item):
                typer.echo(line)
            choice = typer.prompt("[a] aprobar · [r] rechazar · [s] saltar · [q] salir", default="s")

            if choice == "q":
                break
            if choice == "s":
                continue
            if choice == "r":
                review_repo.decide(cur, item["id"], "rejected", actor)
                conn.commit()
                typer.echo("  rechazado")
                continue
            try:
                done = review_flow.approve(cur, item, actor)
                review_repo.decide(cur, item["id"], "approved", actor)
                conn.commit()
                typer.echo(f"  ✓ {done}")
            except (LookupError, ValueError) as error:
                conn.rollback()
                typer.echo(f"  ✗ {error}")


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
    """Comprueba que el dataset semilla sigue intacto (lo nuevo no se cuenta)."""
    with connect() as conn:
        rebuilt = publish.build(conn)
    problems = parity.compare(seed, rebuilt)

    if problems:
        typer.echo(f"✗ {len(problems)} diferencias:")
        for p in problems[:25]:
            typer.echo(f"  {p}")
        raise typer.Exit(1)
    typer.echo("✓ El dataset semilla sigue intacto en el grafo")


if __name__ == "__main__":
    app()
