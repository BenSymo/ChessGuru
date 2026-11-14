select
    username,
    game_uuid,
    ply,
    move_number,
    colour,
    is_player_move,
    san,
    uci,
    piece,
    is_capture,
    is_check,
    is_castle,
    is_promotion,
    fen_before,
    clock_seconds,
    time_spent_seconds
from {{ source('silver', 'silver_moves') }}
