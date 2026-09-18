-- Identificador público de la pelea: no se puede deducir del evento y los apellidos
-- ("du-plessis" tiene dos palabras), así que se guarda.
alter table fights add column slug text;
update fights set slug = id where slug is null;
alter table fights alter column slug set not null;
alter table fights add constraint fights_slug_unique unique (slug);

-- Cuándo se consultó la fuente: parte de la procedencia.
alter table sources add column retrieved_at date;
