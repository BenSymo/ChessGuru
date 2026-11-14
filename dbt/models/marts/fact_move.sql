-- Grain: one row per move (ply) in each game, both sides.
-- is_player_move picks out the analysed player's own moves.
select
    {{ surrogate_key(['m.username', 'm.game_uuid', 'm.ply']) }} as move_key,
    {{ surrogate_key(['m.username', 'm.game_uuid']) }} as game_key,
    cast(strftime(g.end_date, '%Y%m%d') as integer) as date_key,
    m.username,
    m.ply,
    m.move_number,
    m.colour,
    m.is_player_move,
    m.san,
    m.uci,
    m.piece,
    m.is_capture,
    m.is_check,
    m.is_castle,
    m.is_promotion,
    m.fen_before,
    m.clock_seconds,
    m.time_spent_seconds,
    case when g.base_seconds > 0 then m.clock_seconds / g.base_seconds end as clock_fraction_left,
    e.ply is not null as is_analysed,
    e.phase,
    e.label,
    e.is_bad_move,
    e.cp_before,
    e.cp_after,
    e.mate_before,
    e.mate_after,
    e.win_before,
    e.win_after,
    e.win_drop,
    e.cp_loss,
    e.move_accuracy,
    e.best_move_uci,
    e.best_move_san,
    coalesce(p.tags, e.tags) as tags
from {{ ref('stg_moves') }} as m
inner join {{ ref('stg_games') }} as g
    on g.username = m.username and g.game_uuid = m.game_uuid
left join {{ ref('stg_move_evals') }} as e
    on e.username = m.username and e.game_uuid = m.game_uuid and e.ply = m.ply
left join {{ ref('int_player_move_evals') }} as p
    on p.username = m.username and p.game_uuid = m.game_uuid and p.ply = m.ply
