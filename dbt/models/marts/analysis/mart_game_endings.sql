-- How the player's games finish: e.g. how many losses are on time.
select
    username,
    time_class,
    outcome,
    end_reason,
    count(*) as games
from {{ ref('fact_game') }}
group by all
