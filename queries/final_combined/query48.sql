/*
  Optimization procedure:
  1. Materialize the 2002 dates and each dimension's exact union of values
     used by the original three demographic and three address branches.
  2. Drive from those dates into store_sales and apply safe fact-side bounding
     boxes (sales price 50..200 and net profit 0..25000).
  3. Retain all branch-specific status/education/price and state/profit
     correlations after joining. The bounds are supersets only; they do not
     replace the original disjunctions.
  4. Preserve the store join and the original SUM aggregate.
*/
-- Law II: Prefilter dimensions and apply the outer fact bounds before joins.
WITH filtered_dates AS (
    -- Use the baseline year restriction before the fact-table join.
    SELECT d_date_sk
    FROM date_dim
    WHERE d_year = 2002
),
filtered_demographics AS (
    -- Candidate set is the union of valid demographic branches.
    SELECT cd_demo_sk, cd_marital_status, cd_education_status
    FROM customer_demographics
    WHERE (cd_marital_status = 'M'
           AND cd_education_status = '4 yr Degree')
       OR (cd_marital_status = 'U'
           AND cd_education_status = 'College')
       OR (cd_marital_status = 'S'
           AND cd_education_status = '2 yr Degree')
),
filtered_addresses AS (
    -- Candidate states are a safe union; exact state/profit pairings stay below.
    SELECT ca_address_sk, ca_state
    FROM customer_address
    WHERE ca_country = 'United States'
      AND ca_state IN ('NH', 'OK', 'NC', 'MS', 'TX', 'TN', 'CA', 'KS', 'GA')
),
eligible_sales AS (
    -- Law III: Use the date subset to drive the store_sales access.
    SELECT /*+ NO_MERGE(d) */
           ss.ss_cdemo_sk,
           ss.ss_addr_sk,
           ss.ss_store_sk,
           ss.ss_quantity,
           ss.ss_sales_price,
           ss.ss_net_profit
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss
        ON ss.ss_sold_date_sk = d.d_date_sk
    WHERE ss.ss_sales_price BETWEEN 50.00 AND 200.00
      -- This is a superset of all three original profit intervals.
      AND ss.ss_net_profit BETWEEN 0 AND 25000
)
SELECT /*+ NO_MERGE(ss) NO_MERGE(cd) NO_MERGE(ca) */
       SUM(ss_quantity)
FROM eligible_sales ss
STRAIGHT_JOIN store s
    ON s.s_store_sk = ss.ss_store_sk
STRAIGHT_JOIN filtered_demographics cd
    ON cd.cd_demo_sk = ss.ss_cdemo_sk
STRAIGHT_JOIN filtered_addresses ca
    ON ca.ca_address_sk = ss.ss_addr_sk
WHERE (
        -- Preserve the three demographic/price correlations from the baseline.
        (cd.cd_marital_status = 'M'
         AND cd.cd_education_status = '4 yr Degree'
         AND ss.ss_sales_price BETWEEN 100.00 AND 150.00)
     OR (cd.cd_marital_status = 'U'
         AND cd.cd_education_status = 'College'
         AND ss.ss_sales_price BETWEEN 50.00 AND 100.00)
     OR (cd.cd_marital_status = 'S'
         AND cd.cd_education_status = '2 yr Degree'
         AND ss.ss_sales_price BETWEEN 150.00 AND 200.00)
)
AND (
        -- Preserve each state's corresponding net-profit range.
        (ca.ca_state IN ('NH', 'OK', 'NC')
         AND ss.ss_net_profit BETWEEN 0 AND 2000)
     OR (ca.ca_state IN ('MS', 'TX', 'TN')
         AND ss.ss_net_profit BETWEEN 150 AND 3000)
     OR (ca.ca_state IN ('CA', 'KS', 'GA')
         AND ss.ss_net_profit BETWEEN 50 AND 25000)
);
