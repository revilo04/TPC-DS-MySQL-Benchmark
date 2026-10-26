WITH /*+ SET_VAR(join_buffer_size=1073741824) SET_VAR(tmp_table_size=1073741824) SET_VAR(max_heap_table_size=1073741824) */
d1_2002 AS (
    SELECT /*+ NO_MERGE() */ d_date_sk, d_week_seq, d_date
    FROM date_dim
    WHERE d_year = 2002
),
d2_2002 AS (
    SELECT /*+ NO_MERGE() */ d2.d_date_sk, d2.d_week_seq
    FROM date_dim d2
    WHERE d2.d_week_seq IN (SELECT DISTINCT d_week_seq FROM d1_2002)
),
filtered_cs AS (
    SELECT /*+ NO_MERGE() */
           cs.cs_item_sk,
           d1.d_week_seq,
           cs.cs_quantity,
           SUM(CASE WHEN p.p_promo_sk IS NULL THEN 1 ELSE 0 END) AS no_promo_cnt,
           SUM(CASE WHEN p.p_promo_sk IS NOT NULL THEN 1 ELSE 0 END) AS promo_cnt,
           COUNT(*) AS cs_cnt
    FROM d1_2002 d1
    STRAIGHT_JOIN catalog_sales cs
      ON cs.cs_sold_date_sk = d1.d_date_sk
    STRAIGHT_JOIN date_dim d3
      ON cs.cs_ship_date_sk = d3.d_date_sk
     AND d3.d_date > d1.d_date + 5
    LEFT OUTER JOIN promotion p
      ON cs.cs_promo_sk = p.p_promo_sk
    GROUP BY cs.cs_item_sk, d1.d_week_seq, cs.cs_quantity
),
filtered_inv AS (
    SELECT /*+ NO_MERGE() */
           inv.inv_item_sk,
           inv.inv_warehouse_sk,
           d2.d_week_seq,
           inv.inv_quantity_on_hand
    FROM d2_2002 d2
    STRAIGHT_JOIN inventory inv
      ON inv.inv_date_sk = d2.d_date_sk
)
SELECT /*+ BNL(cs, inv) */
       i.i_item_desc,
       w.w_warehouse_name,
       cs.d_week_seq,
       SUM(cs.no_promo_cnt) AS no_promo,
       SUM(cs.promo_cnt) AS promo,
       CAST(SUM(cs.cs_cnt) AS SIGNED) AS total_cnt
FROM filtered_cs cs
STRAIGHT_JOIN filtered_inv inv
  ON cs.cs_item_sk = inv.inv_item_sk
 AND cs.d_week_seq = inv.d_week_seq
 AND inv.inv_quantity_on_hand < cs.cs_quantity
STRAIGHT_JOIN warehouse w
  ON w.w_warehouse_sk = inv.inv_warehouse_sk
STRAIGHT_JOIN item i
  ON i.i_item_sk = cs.cs_item_sk
WHERE EXISTS (
    SELECT 1
    FROM household_demographics
    JOIN catalog_sales ON cs_bill_hdemo_sk = hd_demo_sk
    WHERE hd_buy_potential = ">10000"
    LIMIT 1
)
AND EXISTS (
    SELECT 1
    FROM customer_demographics
    JOIN catalog_sales ON cs_bill_cdemo_sk = cd_demo_sk
    WHERE cd_marital_status = "U"
    LIMIT 1
)
GROUP BY i.i_item_desc, w.w_warehouse_name, cs.d_week_seq
ORDER BY total_cnt DESC, i.i_item_desc, w.w_warehouse_name, cs.d_week_seq
LIMIT 100;
