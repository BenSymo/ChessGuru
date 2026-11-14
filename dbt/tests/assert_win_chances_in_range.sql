select *
from {{ ref('stg_move_evals') }}
where win_before not between 0 and 100
    or win_after not between 0 and 100
    or win_drop < 0
    or move_accuracy not between 0 and 100
