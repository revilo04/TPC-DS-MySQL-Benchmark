/*
  Optimization procedure:
  1. Materialize the exact date-of-month/year window, Williamson County store
     subset, and household rows satisfying every original household filter.
  2. Drive from the filtered dates into store_sales, then join only qualifying
     stores and household demographics before ticket/customer aggregation.
  3. Keep the household ratio CASE expression and grouping keys unchanged;
     join customer only after ticket counts have been computed.

  The repeated county value in the baseline IN list is equivalent to a single
  equality predicate. The vehicle/dependent constraints are not simplified.
*/
-- Law II: Filter the exact date, county, and household domains first.
WITH filtered_dates AS (
    -- Keep the baseline two-day-of-month and three-year date window.
    SELECT d_date_sk
    FROM date_dim
    WHERE d_dom BETWEEN 1 AND 2
      AND d_year IN (1999, 2000, 2001)
),
filtered_stores AS (
    -- All duplicate county literals in the source represent one county value.
    SELECT s_store_sk
    FROM store
    WHERE s_county = 'Williamson County'
),
filtered_households AS (
    -- Preserve buy-potential, positive-vehicle, and dependent/vehicle filters.
    SELECT hd_demo_sk
    FROM household_demographics
    WHERE (hd_buy_potential = '501-1000'
           OR hd_buy_potential = '5001-10000')
      AND hd_vehicle_count > 0
      AND CASE WHEN hd_vehicle_count > 0
               THEN hd_dep_count / hd_vehicle_count
               ELSE NULL END > 1
),
ticket_counts AS (
    -- Law III: Drive the ticket aggregation from filtered dates and dimensions.
    SELECT /*+ NO_MERGE(d) NO_MERGE(s) NO_MERGE(hd) */
           ss.ss_ticket_number,
           ss.ss_customer_sk,
           COUNT(*) AS cnt
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss
        ON ss.ss_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN filtered_stores s
        ON s.s_store_sk = ss.ss_store_sk
    STRAIGHT_JOIN filtered_households hd
        ON hd.hd_demo_sk = ss.ss_hdemo_sk
    GROUP BY ss.ss_ticket_number, ss.ss_customer_sk
    -- Ticket counts are still computed before joining customer attributes.
)
SELECT c.c_last_name,
       c.c_first_name,
       c.c_salutation,
       c.c_preferred_cust_flag,
       tc.ss_ticket_number,
       tc.cnt
FROM ticket_counts tc
STRAIGHT_JOIN customer c
    ON c.c_customer_sk = tc.ss_customer_sk
WHERE tc.cnt BETWEEN 1 AND 5
ORDER BY tc.cnt DESC, c.c_last_name ASC;
