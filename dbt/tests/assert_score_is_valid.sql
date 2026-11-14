-- A game's score is 1 (win), 0.5 (draw) or 0 (loss), never anything else.
select *
from {{ ref('fact_game') }}
where score not in (0, 0.5, 1)
