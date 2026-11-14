-- The player's rating in each time class, one row each time it changes.
-- This feeds the Type 2 (history-keeping) player dimension.
with ratings as (
    select
        username,
        time_class,
        end_time,
        player_rating as rating,
        lag(player_rating) over (
            partition by username, time_class order by end_time, game_uuid
        ) as previous_rating
    from {{ ref('stg_games') }}
),

changes as (
    select username, time_class, end_time as valid_from, rating
    from ratings
    where previous_rating is null or rating != previous_rating
)

select
    username,
    time_class,
    rating,
    valid_from,
    lead(valid_from) over (partition by username, time_class order by valid_from) as valid_to
from changes
