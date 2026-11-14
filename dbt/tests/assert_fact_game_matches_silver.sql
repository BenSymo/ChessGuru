-- Completeness: every silver game reaches the gold fact table, once.
select silver.n as silver_games, gold.n as fact_games
from (select count(*) as n from {{ source('silver', 'silver_games') }}) as silver,
     (select count(*) as n from {{ ref('fact_game') }}) as gold
where silver.n != gold.n
