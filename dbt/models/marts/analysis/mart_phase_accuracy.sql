-- How well the player plays in each phase of the game (analysed games only).
select
    p.username,
    f.time_class,
    p.phase,
    count(distinct p.game_uuid) as games,
    count(*) as moves,
    avg(p.move_accuracy) as avg_accuracy,
    avg(p.cp_loss) as avg_cp_loss,
    count(*) filter (where p.label = 'blunder') as blunders,
    count(*) filter (where p.label = 'mistake') as mistakes,
    count(*) filter (where p.label = 'inaccuracy') as inaccuracies
from {{ ref('int_player_move_evals') }} as p
inner join {{ ref('fact_game') }} as f using (username, game_uuid)
group by all
