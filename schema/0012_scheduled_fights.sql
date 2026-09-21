-- Las peleas anunciadas todavía no tienen resultado: son parte del universo, no un error.
-- Una pelea programada no tiene ganador ni método; una completada, sí.
alter table fights add column status text not null default 'completed'
  check (status in ('scheduled', 'completed'));
alter table fights alter column method drop not null;

alter table fights drop constraint winner_matches_method;
alter table fights add constraint result_matches_status check (
  (status = 'scheduled' and winner_id is null and method is null)
  or (status = 'completed' and method is not null
      and ((winner_id is null) = (method in ('NC', 'DRAW'))))
);
