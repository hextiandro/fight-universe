-- Lo que aprueba una persona también tiene procedencia: la revisión es una fuente más,
-- con alta confianza porque hay un humano detrás.
insert into sources (id, name, url, type, trust)
values ('manual', 'Revisión manual', null, 'manual', 80)
on conflict (id) do nothing;
