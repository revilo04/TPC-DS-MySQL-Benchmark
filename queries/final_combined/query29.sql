WITH /*+ SET_VAR(tmp_table_size=1073741824) SET_VAR(max_heap_table_size=1073741824) */
d1_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_year = 2000 AND d_moy = 4
),
d2_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_year = 2000 AND d_moy BETWEEN 4 AND 7
),
d3_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_year IN (2000, 2001, 2002)
),
ss_sr AS (
    SELECT /*+ NO_MERGE() */
           ss.ss_item_sk,
           ss.ss_store_sk,
           sr.sr_customer_sk,
           ss.ss_quantity,
           sr.sr_return_quantity
    FROM d1_dates d1
    STRAIGHT_JOIN store_sales ss
      ON ss.ss_sold_date_sk = d1.d_date_sk
    STRAIGHT_JOIN store_returns sr
      ON sr.sr_item_sk = ss.ss_item_sk
     AND sr.sr_ticket_number = ss.ss_ticket_number
     AND sr.sr_customer_sk = ss.ss_customer_sk
    STRAIGHT_JOIN d2_dates d2
      ON sr.sr_returned_date_sk = d2.d_date_sk
)
SELECT i.i_item_id,
       i.i_item_desc,
       s.s_store_id,
       s.s_store_name,
       STDDEV_SAMP(m.ss_quantity) AS store_sales_quantity,
       STDDEV_SAMP(m.sr_return_quantity) AS store_returns_quantity,
       STDDEV_SAMP(cs.cs_quantity) AS catalog_sales_quantity
FROM ss_sr m
STRAIGHT_JOIN catalog_sales cs
  ON cs.cs_item_sk = m.ss_item_sk
 AND cs.cs_bill_customer_sk = m.sr_customer_sk
STRAIGHT_JOIN d3_dates d3
  ON cs.cs_sold_date_sk = d3.d_date_sk
STRAIGHT_JOIN store s
  ON s.s_store_sk = m.ss_store_sk
STRAIGHT_JOIN item i
  ON i.i_item_sk = m.ss_item_sk
GROUP BY i.i_item_id, i.i_item_desc, s.s_store_id, s.s_store_name
ORDER BY i.i_item_id, i.i_item_desc, s.s_store_id, s.s_store_name
LIMIT 100;
