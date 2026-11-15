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
    fen_before,
    clock_seconds,
    time_spent_seconds
from {{ source('silver', 'silver_moves') }}
