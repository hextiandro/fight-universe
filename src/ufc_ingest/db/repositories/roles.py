"""Gestión del usuario de solo lectura de la web.

La contraseña nunca se versiona: llega por entorno y se aplica aquí.
"""

import psycopg
from psycopg import sql


def set_web_password(cur: psycopg.Cursor, role: str, password: str) -> None:
    cur.execute(
        sql.SQL("alter role {} with login password {}").format(sql.Identifier(role), sql.Literal(password))
    )


def can_read_tables(cur: psycopg.Cursor, role: str) -> bool:
    """¿El usuario puede leer alguna tabla directamente? Debe ser `False`."""
    cur.execute(
        """
        select bool_or(has_table_privilege(%s, c.oid, 'select')) as can_read
          from pg_class c join pg_namespace n on n.oid = c.relnamespace
         where n.nspname = 'public' and c.relkind = 'r'
        """,
        (role,),
    )
    return bool(cur.fetchone()["can_read"])
