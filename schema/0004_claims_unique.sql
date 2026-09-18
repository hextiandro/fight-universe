-- Idempotencia: el mismo hecho, de la misma fuente, con el mismo valor, es un único claim.
-- Sin esto, reimportar duplicaba la procedencia ("espn-champions" dos veces).
delete from claims c using claims d
 where c.id > d.id
   and c.subject_type = d.subject_type and c.subject_id = d.subject_id
   and c.field = d.field and c.source_id = d.source_id
   and md5(c.value::text) = md5(d.value::text);

create unique index claims_unique_fact
  on claims (subject_type, subject_id, field, source_id, md5(value::text));
