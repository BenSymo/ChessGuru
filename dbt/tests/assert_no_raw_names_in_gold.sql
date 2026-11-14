-- Governance: opponents' real usernames must never reach the gold layer.
select table_name, column_name
from information_schema.columns
where table_schema in ('gold', 'staging', 'intermediate')
    and column_name ilike '%opponent_username%'
