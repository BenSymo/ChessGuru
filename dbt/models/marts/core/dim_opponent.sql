-- Opponents are other people, so they are only known by a keyed hash.
with games as (
    select
        opponent_key,
        opponent_rating,
        row_number() over (partition by opponent_key order by end_time desc) as newest_first
    from {{ ref('stg_games') }}
)

select
    opponent_key,
    opponent_rating as latest_rating,
    cast(floor(opponent_rating / 100) * 100 as integer) as rating_band,
    (select count(*) from games as g where g.opponent_key = games.opponent_key) as games_played
from games
where newest_first = 1
