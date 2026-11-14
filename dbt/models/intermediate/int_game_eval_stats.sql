-- Per game: how many bad moves the player made, and whether they let a
-- winning position slip. "Winning" means a 75%+ chance to win, about +3.
select
    username,
    game_uuid,
    count(*) filter (where label = 'blunder') as blunders,
    count(*) filter (where label = 'mistake') as mistakes,
    count(*) filter (where label = 'inaccuracy') as inaccuracies,
    max(win_before) as peak_win_chance,
    min(ply) filter (where is_bad_move) as first_bad_ply
from {{ ref('int_player_move_evals') }}
group by all
