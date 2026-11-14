-- How the player uses their clock, by stage of the game.
select
    m.username,
    f.time_class,
    case
        when m.move_number <= 10 then '1-10'
        when m.move_number <= 20 then '11-20'
        when m.move_number <= 30 then '21-30'
        when m.move_number <= 40 then '31-40'
        else '41+'
    end as move_range,
    min(m.move_number) as first_move_number,
    count(*) as moves,
    avg(m.time_spent_seconds) as avg_seconds,
    median(m.time_spent_seconds) as median_seconds,
    avg(case when m.clock_fraction_left < 0.1 then 1.0 else 0.0 end) as share_under_10pct_clock
from {{ ref('fact_move') }} as m
inner join {{ ref('fact_game') }} as f using (game_key)
where m.is_player_move and f.time_class != 'daily'
group by all
