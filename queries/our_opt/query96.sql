WITH filtered_time AS (
  SELECT /*+ NO_MERGE() */ t_time_sk
  FROM time_dim
  WHERE t_hour = 8
    AND t_minute >= 30
),
filtered_hdemo AS (
  SELECT /*+ NO_MERGE() */ hd_demo_sk
  FROM household_demographics
  WHERE hd_dep_count = 4
),
filtered_store AS (
  SELECT /*+ NO_MERGE() */ s_store_sk
  FROM store
  WHERE s_store_name = 'ese'
)
SELECT COUNT(*)
FROM filtered_time t
STRAIGHT_JOIN store_sales ss
  ON ss.ss_sold_time_sk = t.t_time_sk
STRAIGHT_JOIN filtered_hdemo hd
  ON ss.ss_hdemo_sk = hd.hd_demo_sk
STRAIGHT_JOIN filtered_store s
  ON ss.ss_store_sk = s.s_store_sk;