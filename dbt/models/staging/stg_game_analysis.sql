select
    username,
    game_uuid,
    engine_depth,
    player_accuracy as engine_accuracy
from {{ source('silver', 'silver_game_analysis') }}
