select distinct
    {{ surrogate_key(['eco_code', 'opening_name']) }} as opening_key,
    eco_code,
    opening_name,
    opening_family
from {{ ref('stg_games') }}
