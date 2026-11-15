select
    username,
    game_uuid,
    ply,
    phase,
    win_before,
    win_after,
    win_drop,
    accuracy as move_accuracy,
    label,
    label in ('mistake', 'blunder') as is_bad_move,
    best_move_uci,
    best_move_san,
    tags
from {{ source('silver', 'silver_move_evals') }}
