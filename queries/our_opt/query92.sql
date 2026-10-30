WITH date_90days AS (
  SELECT /*+ NO_MERGE() */ d_date_sk
  FROM date_dim
  WHERE d_date BETWEEN '2002-01-05' AND CAST('2002-01-05' AS DATE) + INTERVAL 90 DAY
),
filtered_item AS (
  SELECT /*+ NO_MERGE() */ i_item_sk
  FROM item
  WHERE i_manufact_id = 10
),
avg_discount AS (
  SELECT /*+ NO_MERGE() */
    ws.ws_item_sk,
    1.3 * AVG(ws.ws_ext_discount_amt) AS threshold
  FROM date_90days d
  STRAIGHT_JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk
  STRAIGHT_JOIN filtered_item i ON ws.ws_item_sk = i.i_item_sk
  GROUP BY ws.ws_item_sk
)
SELECT SUM(ws.ws_ext_discount_amt) AS "Excess Discount Amount"
FROM date_90days d
STRAIGHT_JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk
STRAIGHT_JOIN filtered_item i ON ws.ws_item_sk = i.i_item_sk
STRAIGHT_JOIN avg_discount ad ON ws.ws_item_sk = ad.ws_item_sk
WHERE ws.ws_ext_discount_amt > ad.threshold;