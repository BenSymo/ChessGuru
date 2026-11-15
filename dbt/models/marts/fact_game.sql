-- Grain: one row per game, from the analysed player's side.
select
    {{ surrogate_key(['g.username', 'g.game_uuid']) }} as game_key,
    g.game_uuid,
    g.username,
    {{ surrogate_key(['g.time_control', 'g.time_class']) }} as time_control_key,
    {{ surrogate_key(['g.eco_code', 'g.opening_name']) }} as opening_key,
    g.end_time,
    g.date_day,
    g.time_class,
    g.rated,
    g.player_colour,
    g.outcome,
    g.score,
    g.end_reason,
    g.player_rating,
    g.plies,
    g.url,
    a.game_uuid is not null as is_analysed,
    a.engine_accuracy,
    s.blunders,
    s.mistakes,
    s.inaccuracies,
    s.peak_win_chance,
    coalesce(s.peak_win_chance >= 75 and g.outcome != 'win', false) as failed_to_convert
from {{ ref('stg_games') }} as g
left join {{ ref('stg_game_analysis') }} as a using (username, game_uuid)
left join {{ ref('int_game_eval_stats') }} as s using (username, game_uuid)
