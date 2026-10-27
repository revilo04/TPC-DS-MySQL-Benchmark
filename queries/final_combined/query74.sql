WITH d_2000_2001 AS (
    SELECT /*+ NO_MERGE() */ d_date_sk, d_year
    FROM date_dim
    WHERE d_year IN (2000, 2001)
),
-- One pass per channel, grouped by the integer customer key (c_customer_id is unique per
-- c_customer_sk). STDDEV_SAMP is computed over each complete (customer, year) group, and the
-- counts keep the existence semantics of the original per-year self-joins.
s_totals AS (
    SELECT /*+ NO_MERGE() */
           ss.ss_customer_sk AS customer_sk,
           STDDEV_SAMP(CASE WHEN d.d_year = 2000 THEN ss.ss_net_paid END) AS first_total,
           STDDEV_SAMP(CASE WHEN d.d_year = 2001 THEN ss.ss_net_paid END) AS sec_total,
           COUNT(CASE WHEN d.d_year = 2000 THEN 1 END) AS first_rows,
           COUNT(CASE WHEN d.d_year = 2001 THEN 1 END) AS sec_rows
    FROM d_2000_2001 d
    STRAIGHT_JOIN store_sales ss
      ON ss.ss_sold_date_sk = d.d_date_sk
    WHERE ss.ss_customer_sk IS NOT NULL
    GROUP BY ss.ss_customer_sk
),
w_totals AS (
    SELECT /*+ NO_MERGE() */
           ws.ws_bill_customer_sk AS customer_sk,
           STDDEV_SAMP(CASE WHEN d.d_year = 2000 THEN ws.ws_net_paid END) AS first_total,
           STDDEV_SAMP(CASE WHEN d.d_year = 2001 THEN ws.ws_net_paid END) AS sec_total,
           COUNT(CASE WHEN d.d_year = 2000 THEN 1 END) AS first_rows,
           COUNT(CASE WHEN d.d_year = 2001 THEN 1 END) AS sec_rows
    FROM d_2000_2001 d
    STRAIGHT_JOIN web_sales ws
      ON ws.ws_sold_date_sk = d.d_date_sk
    WHERE ws.ws_bill_customer_sk IS NOT NULL
    GROUP BY ws.ws_bill_customer_sk
)
SELECT c.c_customer_id AS customer_id,
       c.c_first_name AS customer_first_name,
       c.c_last_name AS customer_last_name
FROM s_totals s
STRAIGHT_JOIN w_totals w
  ON w.customer_sk = s.customer_sk
STRAIGHT_JOIN customer c
  ON c.c_customer_sk = s.customer_sk
WHERE s.first_rows > 0 AND s.sec_rows > 0
  AND w.first_rows > 0 AND w.sec_rows > 0
  AND s.first_total > 0
  AND w.first_total > 0
  AND CASE WHEN w.first_total > 0 THEN w.sec_total / w.first_total ELSE NULL END
    > CASE WHEN s.first_total > 0 THEN s.sec_total / s.first_total ELSE NULL END
ORDER BY 2, 3, 1
LIMIT 100;
