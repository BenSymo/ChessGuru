select distinct
    {{ surrogate_key(['time_control', 'time_class']) }} as time_control_key,
    time_control,
    time_class,
    base_seconds,
    increment_seconds,
    case
        when base_seconds is null then 'Daily'
        when base_seconds < 60 then base_seconds || ' sec'
        else cast(base_seconds // 60 as varchar) || ' min'
    end
    || case when increment_seconds > 0 then ' + ' || increment_seconds || 's' else '' end
        as label
from {{ ref('stg_games') }}
