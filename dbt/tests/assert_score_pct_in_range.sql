select *
from {{ ref('mart_opening_performance') }}
where score_pct < 0 or score_pct > 1
