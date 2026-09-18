-- Modelo canónico de UFC Graph.
-- Principio: ningún dato se escribe "pelado". Las entidades guardan el valor vigente y
-- `claims` guarda de dónde salió, con qué confianza y desde cuándo vale.

create extension if not exists unaccent;   -- "Jiří" = "Jiri"
create extension if not exists pg_trgm;    -- búsqueda tolerante a erratas
create extension if not exists vector;     -- deduplicación de novedades

-- ───────────────────────── Fuentes y documentos crudos ─────────────────────────

create type source_type as enum ('official', 'media', 'reference', 'stats', 'manual');

create table sources (
  id          text primary key,
  name        text not null,
  url         text,
  type        source_type not null,
  -- 0–100: cuánto pesa en la confianza de un candidato
  trust       smallint not null default 50 check (trust between 0 and 100),
  created_at  timestamptz not null default now()
);

-- Respuesta íntegra de la fuente. El hash evita reprocesar lo mismo dos veces.
create table raw_docs (
  id          bigserial primary key,
  source_id   text not null references sources on delete restrict,
  url         text,
  hash        text not null unique,
  fetched_at  timestamptz not null default now(),
  payload     jsonb not null
);

-- ───────────────────────── Entidades ─────────────────────────

create table divisions (
  id        text primary key,
  name      text not null,
  limit_lb  smallint not null,
  ord       smallint not null
);

create type fighter_status as enum ('active', 'inactive', 'retired');

create table fighters (
  id           text primary key,
  -- Identidad estable, separada del nombre: dos homónimos no chocan.
  slug         text not null unique,
  name         text not null,
  nationality  text,
  division_id  text not null references divisions,
  status       fighter_status not null default 'active',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- Alias inequívocos (apodos, transliteraciones). `normalized` es único:
-- un alias no puede apuntar a dos peleadores.
create table fighter_aliases (
  fighter_id  text not null references fighters on delete cascade,
  alias       text not null,
  normalized  text not null unique,
  primary key (fighter_id, normalized)
);

-- Nivel 1 de la resolución de entidades: emparejar por id externo.
create table fighter_external_ids (
  fighter_id  text not null references fighters on delete cascade,
  system      text not null,          -- 'wikidata', 'wikipedia', 'provider'…
  value       text not null,
  primary key (system, value)
);

-- Redirecciones tras fusionar dos peleadores duplicados: los enlaces antiguos siguen vivos.
create table fighter_merges (
  old_id      text primary key,
  new_id      text not null references fighters on delete cascade,
  merged_at   timestamptz not null default now(),
  reason      text
);

create table events (
  id          text primary key,
  slug        text not null unique,
  name        text not null,
  date        date not null,
  venue       text,
  city        text,
  created_at  timestamptz not null default now()
);

create table event_aliases (
  event_id    text not null references events on delete cascade,
  normalized  text not null unique,
  alias       text not null,
  primary key (event_id, normalized)
);

create type fight_method as enum ('KO/TKO', 'SUB', 'UD', 'SD', 'MD', 'NC', 'DRAW');
create type title_stakes as enum ('undisputed', 'vacant-undisputed', 'interim');

create table fights (
  id             text primary key,
  event_id       text not null references events on delete cascade,
  date           date not null,
  division_id    text not null references divisions,
  winner_id      text references fighters,       -- null en NC y empate
  method         fight_method not null,
  method_detail  text,
  round          smallint,
  time           text,
  title          title_stakes,
  -- Orden en la cartelera: 0 = estelar. El planeta muestra los primeros.
  card_position  smallint not null default 0,
  created_at     timestamptz not null default now(),
  constraint winner_matches_method check ((winner_id is null) = (method in ('NC', 'DRAW')))
);

create table fight_participants (
  fight_id    text not null references fights on delete cascade,
  fighter_id  text not null references fighters,
  corner      smallint not null check (corner in (0, 1)),
  primary key (fight_id, fighter_id)
);

create type development_kind as enum (
  'title-vacated', 'title-awarded', 'ranking-change', 'statement', 'fight-expected', 'injury'
);
-- Nivel de certeza del hecho, no de la fuente.
create type development_status as enum ('official', 'confirmed', 'statement', 'reported', 'rumor');

create table developments (
  id          text primary key,
  slug        text not null unique,
  kind        development_kind not null,
  status      development_status not null,
  date        date not null,
  title       text not null,
  summary     text not null,
  -- Para cambios de título: a qué cinturón afecta.
  division_id text references divisions,
  stakes      text check (stakes in ('undisputed', 'interim')),
  holder_id   text references fighters,
  created_at  timestamptz not null default now()
);

create type entity_type as enum ('fighter', 'event', 'division', 'fight');

create table development_entities (
  development_id  text not null references developments on delete cascade,
  entity_type     entity_type not null,
  entity_id       text not null,
  primary key (development_id, entity_type, entity_id)
);

create table rankings (
  division_id  text not null references divisions,
  fighter_id   text not null references fighters,
  position     smallint not null,          -- 0 = campeón
  as_of        date not null,
  source_id    text not null references sources,
  primary key (division_id, as_of, position)
);

-- ───────────────────────── Procedencia e historia ─────────────────────────

create table claims (
  id           bigserial primary key,
  subject_type entity_type not null,
  subject_id   text not null,
  field        text not null,              -- 'record', 'result', 'nationality'…
  value        jsonb not null,
  source_id    text not null references sources,
  raw_doc_id   bigint references raw_docs,
  confidence   smallint not null default 50 check (confidence between 0 and 100),
  verified     boolean not null default false,
  note         text,
  valid_from   date,
  valid_to     date,
  created_at   timestamptz not null default now()
);

create index claims_subject_idx on claims (subject_type, subject_id, field);

-- ───────────────────────── Ingestión y revisión ─────────────────────────

create type review_state as enum ('pending', 'approved', 'rejected');

create table review_queue (
  id          bigserial primary key,
  candidate   jsonb not null,             -- hecho propuesto, con sus menciones sin resolver
  reason      text not null,              -- por qué necesita revisión
  confidence  smallint not null default 50,
  raw_doc_id  bigint references raw_docs,
  state       review_state not null default 'pending',
  decided_by  text,
  decided_at  timestamptz,
  created_at  timestamptz not null default now()
);

create index review_queue_pending_idx on review_queue (state, created_at);

create table change_log (
  id      bigserial primary key,
  actor   text not null,                  -- 'pipeline:wikipedia-events', 'human:asio'
  action  text not null,                  -- 'insert', 'update', 'merge', 'publish'…
  entity  text not null,                  -- 'fighter:f_01j…'
  before  jsonb,
  after   jsonb,
  at      timestamptz not null default now()
);

create table job_runs (
  id          bigserial primary key,
  job         text not null,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  ok          boolean,
  stats       jsonb,                      -- documentos, candidatos, pendientes…
  error       text
);

-- ───────────────────────── Publicación y vectores ─────────────────────────

-- Cada publicación queda guardada: permite el "antes y después" de un evento y
-- reproducir una imagen ya difundida en redes.
create table published_versions (
  id            bigserial primary key,
  published_at  timestamptz not null default now(),
  counts        jsonb not null,
  payload       jsonb not null
);

create table embeddings (
  entity_type  entity_type not null,
  entity_id    text not null,
  model        text not null,
  vector       vector(1536) not null,
  created_at   timestamptz not null default now(),
  primary key (entity_type, entity_id, model)
);

-- ───────────────────────── Índices de búsqueda ─────────────────────────

create index fighters_name_trgm on fighters using gin (name gin_trgm_ops);
create index fighter_aliases_trgm on fighter_aliases using gin (normalized gin_trgm_ops);
create index events_name_trgm on events using gin (name gin_trgm_ops);
create index developments_text_idx on developments
  using gin (to_tsvector('simple', title || ' ' || summary));
create index fights_event_idx on fights (event_id);
create index fights_date_idx on fights (date desc);
create index developments_date_idx on developments (date desc);
