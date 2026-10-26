/*
  Optimization procedure:
  1. Restrict dates to 2001 and materialize each dimension's exact union of
     values needed by the original disjunctive branches: household dependent
     counts, demographic status/education pairs, and address country/states.
  2. Drive from the filtered date keys into store_sales. Apply safe fact-side
     bounding boxes (sales price 50..200 and net profit 50..300) before
     materializing eligible_sales.
  3. Retain the original correlated demographic/price/dependent-count and
     address/state/profit OR branches after joining the filtered dimensions.
     The broad bounds only remove rows outside every branch; they do not allow
     cross-branch combinations.
  4. Preserve all four aggregates and their original output labels.

  TPC-DS_report.tex illustrates this query with different branch constants.
  This implementation preserves the actual qmod/query13.sql values.
*/
-- Law II: Build exact dimension candidate sets and a safe fact-side bounding box.
WITH filtered_dates AS (
    -- Keep the original target year; all later joins use these date keys.
    SELECT d_date_sk
    FROM date_dim
    WHERE d_year = 2001
),
filtered_households AS (
    -- The three baseline branches use only dependent counts 1 and 3.
    SELECT hd_demo_sk, hd_dep_count
    FROM household_demographics
    WHERE hd_dep_count IN (1, 3)
),
filtered_demographics AS (
    -- Preserve each status/education pairing instead of splitting the OR lists.
    SELECT cd_demo_sk, cd_marital_status, cd_education_status
    FROM customer_demographics
    WHERE (cd_marital_status = 'S'
           AND cd_education_status = 'Secondary')
       OR (cd_marital_status = 'U'
           AND cd_education_status = '4 yr Degree')
       OR (cd_marital_status = 'W'
           AND cd_education_status = '2 yr Degree')
),
filtered_addresses AS (
    -- Union of the baseline state branches; country remains part of the filter.
    SELECT ca_address_sk, ca_state
    FROM customer_address
    WHERE ca_country = 'United States'
      AND ca_state IN ('IA', 'MN', 'MT', 'AR', 'IN', 'TX', 'TN', 'NE', 'WV')
),
-- Law III: Materialize date-driven eligible sales before probing dimensions.
eligible_sales AS (
    SELECT /*+ NO_MERGE(d) */
           ss.ss_hdemo_sk,
           ss.ss_cdemo_sk,
           ss.ss_addr_sk,
           ss.ss_store_sk,
           ss.ss_quantity,
           ss.ss_sales_price,
           ss.ss_ext_sales_price,
           ss.ss_ext_wholesale_cost,
           ss.ss_net_profit
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss
        ON ss.ss_sold_date_sk = d.d_date_sk
    WHERE ss.ss_sales_price BETWEEN 50.00 AND 200.00
      -- Superset bounds only; the exact branch ranges remain below.
      AND ss.ss_net_profit BETWEEN 50 AND 300
)
SELECT /*+ NO_MERGE(ss) NO_MERGE(hd) NO_MERGE(cd) NO_MERGE(ca) */
       AVG(ss_quantity),
       AVG(ss_ext_sales_price),
       AVG(ss_ext_wholesale_cost),
       SUM(ss_ext_wholesale_cost)
FROM eligible_sales ss
STRAIGHT_JOIN store s
    ON s.s_store_sk = ss.ss_store_sk
STRAIGHT_JOIN filtered_households hd
    ON hd.hd_demo_sk = ss.ss_hdemo_sk
STRAIGHT_JOIN filtered_demographics cd
    ON cd.cd_demo_sk = ss.ss_cdemo_sk
STRAIGHT_JOIN filtered_addresses ca
    ON ca.ca_address_sk = ss.ss_addr_sk
WHERE (
        -- Keep status, education, price, and dependent-count branch pairings.
        (cd.cd_marital_status = 'S'
         AND cd.cd_education_status = 'Secondary'
         AND ss.ss_sales_price BETWEEN 100.00 AND 150.00
         AND hd.hd_dep_count = 3)
     OR (cd.cd_marital_status = 'U'
         AND cd.cd_education_status = '4 yr Degree'
         AND ss.ss_sales_price BETWEEN 50.00 AND 100.00
         AND hd.hd_dep_count = 1)
     OR (cd.cd_marital_status = 'W'
         AND cd.cd_education_status = '2 yr Degree'
         AND ss.ss_sales_price BETWEEN 150.00 AND 200.00
         AND hd.hd_dep_count = 1)
)
AND (
        -- Keep state/profit pairings; independent lists would admit false matches.
        (ca.ca_state IN ('IA', 'MN', 'MT')
         AND ss.ss_net_profit BETWEEN 100 AND 200)
     OR (ca.ca_state IN ('AR', 'IN', 'TX')
         AND ss.ss_net_profit BETWEEN 150 AND 300)
     OR (ca.ca_state IN ('TN', 'NE', 'WV')
         AND ss.ss_net_profit BETWEEN 50 AND 250)
);
