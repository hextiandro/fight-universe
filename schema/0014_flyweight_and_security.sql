-- 1. Faltaba el peso mosca: el conector lo encontró en las carteleras reales.
insert into divisions (id, name, limit_lb, ord)
values ('flyweight', 'Flyweight', 125, 8)
on conflict (id) do nothing;

-- 2. `create or replace function` descarta los atributos que no se repiten, así que las
-- migraciones que redefinieron published_graph() le quitaron el "ejecuta como su dueño"
-- y la web perdió el permiso (42501). Se vuelven a aplicar aquí.
alter function published_graph() security definer;
alter function published_graph() set search_path = public, pg_temp;
revoke execute on function published_graph() from public;
grant execute on function published_graph() to ufc_web;
