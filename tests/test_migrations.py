"""Las migraciones deben estar numeradas, ser únicas y no editarse tras aplicarse."""

from ufc_ingest.config import settings


def test_migrations_numeradas_y_unicas() -> None:
    files = sorted(settings.schema_dir.glob("*.sql"))
    assert files, "no hay migraciones en schema/"
    versions = [f.stem.split("_")[0] for f in files]
    assert versions == sorted(versions), "las migraciones deben ir en orden"
    assert len(set(versions)) == len(versions), "hay números de migración repetidos"
