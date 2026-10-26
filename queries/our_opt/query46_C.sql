/*
  Optimization procedure:
  1. Materialize the exact three-year/week-day set and the two qualifying
     dimension subsets. The repeated store-city values in the baseline reduce
     to the same two-value IN set.
  2. Start at the bounded dates and drive into store_sales, then probe store,
     household_demographics, and customer_address by their keys.
  3. Keep the inner ticket/customer/address/city grouping exactly as written:
     ss_addr_sk is part of the grouping even though it is not projected.
  4. Preserve the outer current-address-vs-bought-city inequality, ordering,
     and limit.
*/
-- Law II: Filter date, city, and household candidates before fact access.
WITH filtered_dates AS (
    -- Restrict to the exact weekday and three-year range in the baseline.
    SELECT d_date_sk
    FROM date_dim
    WHERE d_dow IN (6, 0)
      AND d_year IN (2000, 2001, 2002)
),
filtered_stores AS (
    -- Repeated city literals in the source have no additional effect.
    SELECT s_store_sk
    FROM store
    WHERE s_city IN ('Fairview', 'Midway')
),
filtered_households AS (
    -- Preserve the original household OR without assuming domain constraints.
    SELECT hd_demo_sk
    FROM household_demographics
    WHERE hd_dep_count = 6
       OR hd_vehicle_count = 4
),
ticket_totals AS (
    -- Law III: Drive from bounded dates and aggregate before customer lookup.
    SELECT /*+ NO_MERGE(d) NO_MERGE(s) NO_MERGE(hd) */
           ss.ss_ticket_number,
           ss.ss_customer_sk,
           ca.ca_city AS bought_city,
           SUM(ss.ss_coupon_amt) AS amt,
           SUM(ss.ss_net_profit) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss
        ON ss.ss_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN filtered_stores s
        ON s.s_store_sk = ss.ss_store_sk
    STRAIGHT_JOIN filtered_households hd
        ON hd.hd_demo_sk = ss.ss_hdemo_sk
    STRAIGHT_JOIN customer_address ca
        ON ca.ca_address_sk = ss.ss_addr_sk
    GROUP BY ss.ss_ticket_number,
             ss.ss_customer_sk,
             -- Keep address key because the source groups at address granularity.
             ss.ss_addr_sk,
             ca.ca_city
)
SELECT c.c_last_name,
       c.c_first_name,
       current_addr.ca_city,
       dn.bought_city,
       dn.ss_ticket_number,
       dn.amt,
       dn.profit
FROM ticket_totals dn
STRAIGHT_JOIN customer c
    ON c.c_customer_sk = dn.ss_customer_sk
STRAIGHT_JOIN customer_address current_addr
    ON current_addr.ca_address_sk = c.c_current_addr_sk
WHERE current_addr.ca_city <> dn.bought_city
ORDER BY c.c_last_name,
         c.c_first_name,
         current_addr.ca_city,
         dn.bought_city,
         dn.ss_ticket_number
LIMIT 100;
