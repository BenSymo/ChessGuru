-- Slowly changing dimension, Type 2: a new row each time the player's rating
-- changes, so history is kept. valid_to is null on the current row.
select
    {{ surrogate_key(['username', 'time_class', 'valid_from']) }} as player_key,
    username,
    time_class,
    rating,
    valid_from,
    valid_to,
    valid_to is null as is_current
from {{ ref('int_rating_changes') }}
