-- Every analysed move must match a real move in silver.
select e.username, e.game_uuid, e.ply
from {{ ref('stg_move_evals') }} as e
left join {{ ref('stg_moves') }} as m using (username, game_uuid, ply)
where m.ply is null
