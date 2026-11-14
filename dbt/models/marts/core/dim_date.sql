-- One row per day between the first and last game.
with bounds as (
    select min(end_date) as first_day, max(end_date) as last_day
    from {{ ref('stg_games') }}
),

days as (
    select cast(unnest(generate_series(
        cast(first_day as timestamp), cast(last_day as timestamp), interval 1 day
    )) as date) as date_day
    from bounds
    where first_day is not null
)

select
    cast(strftime(date_day, '%Y%m%d') as integer) as date_key,
    date_day,
    year(date_day) as year,
    month(date_day) as month,
    strftime(date_day, '%B') as month_name,
    isodow(date_day) as day_of_week,
    strftime(date_day, '%A') as day_name,
    isodow(date_day) in (6, 7) as is_weekend
from days
