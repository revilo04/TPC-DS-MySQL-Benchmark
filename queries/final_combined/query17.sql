WITH /*+ SET_VAR(tmp_table_size=1073741824) SET_VAR(max_heap_table_size=1073741824) */
d1_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_quarter_name = "2002Q1"
),
d23_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_quarter_name IN ("2002Q1", "2002Q2", "2002Q3")
),
sr_filtered AS (
    SELECT /*+ NO_MERGE() */
           sr.sr_item_sk,
           sr.sr_ticket_number,
           sr.sr_customer_sk,
           sr.sr_return_quantity
    FROM d23_dates d2
    STRAIGHT_JOIN store_returns sr ON sr.sr_returned_date_sk = d2.d_date_sk
),
ss_sr AS (
    SELECT /*+ NO_MERGE() */
           ss.ss_item_sk,
           ss.ss_store_sk,
           sr.sr_customer_sk,
           ss.ss_quantity,
           sr.sr_return_quantity
    FROM sr_filtered sr
    STRAIGHT_JOIN store_sales ss
      ON ss.ss_item_sk = sr.sr_item_sk
     AND ss.ss_ticket_number = sr.sr_ticket_number
     AND ss.ss_customer_sk = sr.sr_customer_sk
    STRAIGHT_JOIN d1_dates d1
      ON ss.ss_sold_date_sk = d1.d_date_sk
)
SELECT i.i_item_id,
       i.i_item_desc,
       s.s_state,
       COUNT(m.ss_quantity) AS store_sales_quantitycount,
       AVG(m.ss_quantity) AS store_sales_quantityave,
       STDDEV_SAMP(m.ss_quantity) AS store_sales_quantitystdev,
       STDDEV_SAMP(m.ss_quantity) / AVG(m.ss_quantity) AS store_sales_quantitycov,
       COUNT(m.sr_return_quantity) AS store_returns_quantitycount,
       AVG(m.sr_return_quantity) AS store_returns_quantityave,
       STDDEV_SAMP(m.sr_return_quantity) AS store_returns_quantitystdev,
       STDDEV_SAMP(m.sr_return_quantity) / AVG(m.sr_return_quantity) AS store_returns_quantitycov,
       COUNT(cs.cs_quantity) AS catalog_sales_quantitycount,
       AVG(cs.cs_quantity) AS catalog_sales_quantityave,
       STDDEV_SAMP(cs.cs_quantity) AS catalog_sales_quantitystdev,
       STDDEV_SAMP(cs.cs_quantity) / AVG(cs.cs_quantity) AS catalog_sales_quantitycov
FROM ss_sr m
STRAIGHT_JOIN catalog_sales cs
  ON cs.cs_item_sk = m.ss_item_sk
 AND cs.cs_bill_customer_sk = m.sr_customer_sk
STRAIGHT_JOIN d23_dates d3
  ON cs.cs_sold_date_sk = d3.d_date_sk
STRAIGHT_JOIN store s
  ON s.s_store_sk = m.ss_store_sk
STRAIGHT_JOIN item i
  ON i.i_item_sk = m.ss_item_sk
GROUP BY i.i_item_id, i.i_item_desc, s.s_state
ORDER BY i.i_item_id, i.i_item_desc, s.s_state
LIMIT 100;
