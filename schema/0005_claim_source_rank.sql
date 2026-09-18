-- El orden de las fuentes importa: la primera es la principal. Se conserva.
alter table claims add column source_rank smallint not null default 0;
