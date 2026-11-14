-- Grain: one row per game, from the analysed player's side.
select
    {{ surrogate_key(['g.username', 'g.game_uuid']) }} as game_key,
    g.game_uuid,
    g.username,
    cast(strftime(g.end_date, '%Y%m%d') as integer) as date_key,
    {{ surrogate_key(['g.time_control', 'g.time_class']) }} as time_control_key,
    {{ surrogate_key(['g.eco_code', 'g.opening_name']) }} as opening_key,
    g.opponent_key,
    p.player_key,
    g.end_time,
    g.end_hour_utc,
    g.time_class,
    g.rated,
    g.player_colour,
    g.outcome,
    g.score,
    g.end_reason,
    g.player_rating,
    g.opponent_rating,
    g.rating_diff,
    g.plies,
    g.full_moves,
    g.player_accuracy,
    g.opponent_accuracy,
    g.url,
    a.game_uuid is not null as is_analysed,
    a.engine_depth,
    a.engine_accuracy,
    a.opponent_engine_accuracy,
    s.blunders,
    s.mistakes,
    s.inaccuracies,
    s.peak_win_chance,
    coalesce(s.peak_win_chance >= 75 and g.outcome != 'win', false) as failed_to_convert,
    -- 1 = the player's newest game. Lets the app pick "the last N games".
    row_number() over (partition by g.username order by g.end_time desc, g.game_uuid) as recency_rank
from {{ ref('stg_games') }} as g
left join {{ ref('stg_game_analysis') }} as a using (username, game_uuid)
left join {{ ref('int_game_eval_stats') }} as s using (username, game_uuid)
left join {{ ref('dim_player') }} as p
    on p.username = g.username
    and p.time_class = g.time_class
    and g.end_time >= p.valid_from
    and (g.end_time < p.valid_to or p.valid_to is null)
