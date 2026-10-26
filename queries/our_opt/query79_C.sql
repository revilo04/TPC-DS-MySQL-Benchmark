/*
  Optimization procedure:
  1. Materialize the exact weekday/year range, employee-count store subset,
     and household rows satisfying the original OR condition.
  2. Drive from the filtered dates into store_sales, then join qualifying
     stores and household rows before calculating ticket totals.
  3. Retain ss_addr_sk in the inner GROUP BY even though it is not projected;
     keep the customer lookup after aggregation and preserve the city substring,
     order, and limit.

  The household OR is intentionally not simplified: hd_vehicle_count > -1
  must keep its exact SQL behavior for NULL and all stored values.
*/
-- Law II: Push weekday/year, employee-count, and household filters downward.
WITH filtered_dates AS (
    -- Keep the original weekday and inclusive three-year range.
    SELECT d_date_sk
    FROM date_dim
    WHERE d_dow = 1
      AND d_year IN (1999, 2000, 2001)
),
filtered_stores AS (
    -- Limit stores by the baseline employee-count range.
    SELECT s_store_sk, s_city
    FROM store
    WHERE s_number_employees BETWEEN 200 AND 295
),
filtered_households AS (
    -- Retain this OR exactly, including SQL NULL behavior.
    SELECT hd_demo_sk
    FROM household_demographics
    WHERE hd_dep_count = 9
       OR hd_vehicle_count > -1
),
ticket_totals AS (
    -- Law III: Start from the bounded date set before aggregating ticket rows.
    SELECT /*+ NO_MERGE(d) NO_MERGE(s) NO_MERGE(hd) */
           ss.ss_ticket_number,
           ss.ss_customer_sk,
           s.s_city,
           SUM(ss.ss_coupon_amt) AS amt,
           SUM(ss.ss_net_profit) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss
        ON ss.ss_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN filtered_stores s
        ON s.s_store_sk = ss.ss_store_sk
    STRAIGHT_JOIN filtered_households hd
        ON hd.hd_demo_sk = ss.ss_hdemo_sk
    GROUP BY ss.ss_ticket_number,
             ss.ss_customer_sk,
             -- Address key remains a grouping key as in the baseline.
             ss.ss_addr_sk,
             s.s_city
)
SELECT c.c_last_name,
       c.c_first_name,
       SUBSTR(s_city, 1, 30),
       tt.ss_ticket_number,
       tt.amt,
       tt.profit
FROM ticket_totals tt
STRAIGHT_JOIN customer c
    ON c.c_customer_sk = tt.ss_customer_sk
ORDER BY c.c_last_name,
         c.c_first_name,
         SUBSTR(s_city, 1, 30),
         tt.profit
LIMIT 100;
