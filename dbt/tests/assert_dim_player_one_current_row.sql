-- Type 2 dimension: exactly one current row per player and time class,
-- and no row ends before it starts.
select username, time_class, count(*) filter (where is_current) as current_rows
from {{ ref('dim_player') }}
group by all
having count(*) filter (where is_current) != 1
    or count(*) filter (where valid_to <= valid_from) > 0
