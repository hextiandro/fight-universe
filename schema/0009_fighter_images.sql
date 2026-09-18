-- Añade la foto del peleador (con su autor y licencia) al grafo publicado.
-- El grafo publicado, definido una sola vez en SQL. Lo consumen el pipeline (Python)
-- y la web (Next.js), así que su forma no puede divergir entre ambos.
--
-- Reglas: los ids públicos son los slugs (los internos no salen), los campos nulos se
-- omiten y el orden de las fuentes se respeta (la primera es la principal).
create or replace function published_graph() returns jsonb
language sql stable as $$
with claim as (
  select subject_type, subject_id, field,
         (array_agg(value order by source_rank, source_id))[1] as value,
         array_agg(source_id order by source_rank, source_id) as source_ids,
         bool_or(verified) as verified,
         min(note) as note,
         min(valid_from) as valid_from
    from claims
   where source_id <> 'seed-dataset-v1' or field = 'image'
   group by subject_type, subject_id, field
),
provenance as (
  select subject_type, subject_id, field,
         jsonb_strip_nulls(jsonb_build_object(
           'sourceIds', to_jsonb(source_ids), 'verified', verified, 'note', note
         )) as value
    from claim
)
select jsonb_build_object(
  'divisions', (
    select coalesce(jsonb_agg(jsonb_build_object(
      'id', id, 'name', name, 'limitLb', limit_lb, 'order', ord
    ) order by ord), '[]'::jsonb) from divisions
  ),
  'sources', (
    select coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
      'id', id, 'name', name, 'url', coalesce(url, ''), 'type', type::text,
      'retrievedAt', retrieved_at::text
    )) order by id), '[]'::jsonb) from sources
  ),
  'fighters', (
    select coalesce(jsonb_agg(f.value order by f.slug), '[]'::jsonb) from (
      select fi.slug, jsonb_strip_nulls(jsonb_build_object(
        'id', fi.slug,
        'name', fi.name,
        'aliases', (
          select case when count(*) = 0 then null else jsonb_agg(a.alias order by a.alias) end
            from fighter_aliases a where a.fighter_id = fi.id
        ),
        'nationality', fi.nationality,
        'divisionId', fi.division_id,
        'record', (
          select jsonb_strip_nulls(jsonb_build_object(
            'value', c.value, 'asOf', c.valid_from::text,
            'sourceIds', to_jsonb(c.source_ids), 'verified', c.verified, 'note', c.note
          )) from claim c
           where c.subject_type = 'fighter' and c.subject_id = fi.id and c.field = 'record'
        ),
        -- Foto con licencia libre: la atribución viaja con el dato
        'image', (
          select c.value from claim c
           where c.subject_type = 'fighter' and c.subject_id = fi.id and c.field = 'image'
        )
      )) as value
      from fighters fi
    ) f
  ),
  'events', (
    select coalesce(jsonb_agg(e.value order by e.date, e.slug), '[]'::jsonb) from (
      select ev.date, ev.slug, jsonb_strip_nulls(jsonb_build_object(
        'id', ev.slug, 'name', ev.name, 'date', ev.date::text,
        'venue', ev.venue, 'city', ev.city,
        'provenance', coalesce(
          (select p.value from provenance p
            where p.subject_type = 'event' and p.subject_id = ev.id and p.field = 'existence'),
          jsonb_build_object('sourceIds', '[]'::jsonb, 'verified', false)
        )
      )) as value
      from events ev
    ) e
  ),
  'fights', (
    select coalesce(jsonb_agg(b.value order by b.date, b.id), '[]'::jsonb) from (
      select fg.date, fg.id, jsonb_strip_nulls(jsonb_build_object(
        'id', fg.slug,
        'eventId', (select slug from events where id = fg.event_id),
        'date', fg.date::text,
        'divisionId', fg.division_id,
        'fighterIds', (
          select jsonb_agg(pf.slug order by p.corner)
            from fight_participants p join fighters pf on pf.id = p.fighter_id
           where p.fight_id = fg.id
        ),
        'method', fg.method::text,
        'methodDetail', fg.method_detail,
        'round', fg.round,
        'time', fg.time,
        'title', fg.title::text,
        'provenance', coalesce(
          (select p.value from provenance p
            where p.subject_type = 'fight' and p.subject_id = fg.id and p.field = 'result'),
          jsonb_build_object('sourceIds', '[]'::jsonb, 'verified', false)
        )
      )) || jsonb_build_object(
        -- null significa "sin resultado": el campo debe existir igualmente
        'winnerId', to_jsonb((select slug from fighters where id = fg.winner_id))
      ) as value
      from fights fg
    ) b
  ),
  'developments', (
    select coalesce(jsonb_agg(d.value order by d.date, d.slug), '[]'::jsonb) from (
      select dv.date, dv.slug, jsonb_strip_nulls(jsonb_build_object(
        'id', dv.slug,
        'kind', dv.kind::text,
        'status', dv.status::text,
        'date', dv.date::text,
        'title', dv.title,
        'summary', dv.summary,
        'about', (
          select coalesce(jsonb_agg(jsonb_build_object(
            'type', de.entity_type::text,
            'id', coalesce(
              (select slug from fighters where id = de.entity_id and de.entity_type = 'fighter'),
              (select slug from events where id = de.entity_id and de.entity_type = 'event'),
              (select slug from fights where id = de.entity_id and de.entity_type = 'fight'),
              de.entity_id
            )
          )), '[]'::jsonb)
            from development_entities de where de.development_id = dv.id
        ),
        'provenance', coalesce(
          (select p.value from provenance p
            where p.subject_type = 'development' and p.subject_id = dv.id and p.field = 'existence'),
          jsonb_build_object('sourceIds', '[]'::jsonb, 'verified', false)
        )
      )) || case when dv.division_id is null then '{}'::jsonb else jsonb_build_object(
        'titleChange', jsonb_build_object(
          'divisionId', dv.division_id, 'stakes', dv.stakes,
          'holderId', to_jsonb((select slug from fighters where id = dv.holder_id))
        )
      ) end as value
      from developments dv
    ) d
  )
);
$$;
