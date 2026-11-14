-- Why the player's bad moves went wrong, by phase. A move can have several
-- reasons, or none we can name ("other").
with tagged as (
    select
        username,
        game_uuid,
        phase,
        win_drop,
        unnest(case when len(tags) = 0 then ['other'] else tags end) as tag
    from {{ ref('int_player_move_evals') }}
    where is_bad_move or list_contains(tags, 'missed_mate')
)

select
    t.username,
    f.time_class,
    t.phase,
    t.tag,
    count(*) as moves,
    count(distinct t.game_uuid) as games,
    avg(t.win_drop) as avg_win_drop
from tagged as t
inner join {{ ref('fact_game') }} as f using (username, game_uuid)
group by all
