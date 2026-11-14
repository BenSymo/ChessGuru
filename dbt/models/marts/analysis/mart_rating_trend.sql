-- The player's rating at the end of each day they played, per time class.
select
    f.username,
    f.time_class,
    d.date_day,
    arg_max(f.player_rating, f.end_time) as rating,
    count(*) as games,
    sum(f.score) as points
from {{ ref('fact_game') }} as f
inner join {{ ref('dim_date') }} as d using (date_key)
group by all
