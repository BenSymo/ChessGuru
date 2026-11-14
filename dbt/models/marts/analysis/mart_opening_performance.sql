-- How each opening goes for the player, by colour and time class.
-- `points` and `games` are kept so the app can add groups together correctly.
select
    f.username,
    f.time_class,
    f.player_colour,
    o.opening_family,
    count(*) as games,
    count(*) filter (where f.outcome = 'win') as wins,
    count(*) filter (where f.outcome = 'draw') as draws,
    count(*) filter (where f.outcome = 'loss') as losses,
    sum(f.score) as points,
    sum(f.score) / count(*) as score_pct,
    avg(f.player_accuracy) as avg_accuracy,
    max(f.end_time) as last_played
from {{ ref('fact_game') }} as f
inner join {{ ref('dim_opening') }} as o using (opening_key)
group by all
