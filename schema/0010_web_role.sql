-- Usuario de solo lectura para la web (mínimo privilegio).
--
-- No puede leer ninguna tabla: solo ejecutar `published_graph()`, que pasa a ejecutarse
-- con los permisos de su dueño. Así la web no ve la cola de revisión, ni los borradores,
-- ni los documentos crudos: solo el grafo ya publicado.
--
-- La contraseña NO va aquí (este repositorio es público). Se fija aparte con
-- `ufc-ingest set-web-password`, que la lee del entorno.

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'ufc_web') then
    create role ufc_web nologin;
  end if;
end
$$;

grant connect on database postgres to ufc_web;
grant usage on schema public to ufc_web;

-- El dueño presta sus permisos solo dentro de esta función.
alter function published_graph() security definer;
alter function published_graph() set search_path = public, pg_temp;

revoke execute on function published_graph() from public;
grant execute on function published_graph() to ufc_web;
