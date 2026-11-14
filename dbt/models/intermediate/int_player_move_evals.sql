-- The player's own analysed moves, with clock context and every reason the
-- move went wrong. `low_clock` is added here: a bad move made with under 10%
-- of the starting clock left.
select
    m.username,
    m.game_uuid,
    m.ply,
    m.move_number,
    e.phase,
    e.label,
    e.is_bad_move,
    e.win_before,
    e.win_drop,
    e.cp_loss,
    e.move_accuracy,
    m.clock_seconds,
    case when g.base_seconds > 0 then m.clock_seconds / g.base_seconds end as clock_fraction_left,
    list_concat(
        e.tags,
        case
            when e.is_bad_move and g.base_seconds > 0 and m.clock_seconds / g.base_seconds < 0.1
                then ['low_clock']
            else []
        end
    ) as tags
from {{ ref('stg_moves') }} as m
inner join {{ ref('stg_move_evals') }} as e using (username, game_uuid, ply)
inner join {{ ref('stg_games') }} as g using (username, game_uuid)
where m.is_player_move
