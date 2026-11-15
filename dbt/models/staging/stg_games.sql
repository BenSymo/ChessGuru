-- One row per game per analysed player, with a numeric score.
select
    username,
    game_uuid,
    url,
    end_time,
    cast(timezone('UTC', end_time) as date) as date_day,
    time_class,
    time_control,
    base_seconds,
    increment_seconds,
    rated,
    player_colour,
    player_rating,
    outcome,
    case outcome when 'win' then 1.0 when 'draw' then 0.5 else 0.0 end as score,
    end_reason,
    eco_code,
    coalesce(opening_name, 'Unknown') as opening_name,
    coalesce(opening_family, 'Unknown') as opening_family,
    plies
from {{ source('silver', 'silver_games') }}
