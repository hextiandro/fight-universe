-- `create or replace function` descarta los atributos de la función: la 0015 la
-- redefinió y se perdieron `security definer` y el grant, así que la web volvió a
-- recibir 42501. Se vuelven a aplicar.
--
-- Convención: toda migración que redefina `published_graph()` debe terminar con
-- este bloque. `tests/test_schema.py` lo comprueba.
alter function published_graph() security definer;
alter function published_graph() set search_path = public, pg_temp;
revoke execute on function published_graph() from public;
grant execute on function published_graph() to ufc_web;
