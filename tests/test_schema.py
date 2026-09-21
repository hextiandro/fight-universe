"""Reglas sobre las migraciones, no sobre el código.

`create or replace function` descarta los atributos de la función (security definer,
search_path) y los permisos concedidos. Ya nos costó dos incidentes de 42501 en la web:
esta prueba impide el tercero.
"""

from pathlib import Path

SCHEMA = Path(__file__).resolve().parents[1] / "schema"


def test_redefining_published_graph_restores_its_grants() -> None:
    offenders = []
    for path in sorted(SCHEMA.glob("*.sql")):
        sql = path.read_text().lower()
        if "create or replace function published_graph" not in sql:
            continue
        restores = "security definer" in sql and "grant execute on function published_graph()" in sql
        if not restores:
            # La migración siguiente puede repararlo, y así ocurrió históricamente.
            following = [p for p in sorted(SCHEMA.glob("*.sql")) if p.name > path.name]
            if any("grant execute on function published_graph()" in p.read_text().lower() for p in following):
                continue
            offenders.append(path.name)
    assert not offenders, (
        f"Estas migraciones redefinen published_graph() sin devolverle sus permisos: {offenders}"
    )


def test_last_migration_leaves_the_function_granted() -> None:
    """Sea cual sea el orden, el estado final debe conceder execute a ufc_web."""
    last_touch = max(
        (p for p in SCHEMA.glob("*.sql") if "published_graph()" in p.read_text().lower()),
        key=lambda p: p.name,
    )
    assert "grant execute on function published_graph() to ufc_web" in last_touch.read_text().lower()
