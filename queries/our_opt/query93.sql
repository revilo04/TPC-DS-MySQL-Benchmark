WITH target_reason AS (
  SELECT /*+ NO_MERGE() */ r_reason_sk
  FROM reason
  WHERE r_reason_desc = 'reason 70'
),
filtered_returns AS (
  SELECT /*+ NO_MERGE() */
    sr.sr_item_sk,
    sr.sr_ticket_number,
    sr.sr_return_quantity
  FROM target_reason r
  STRAIGHT_JOIN store_returns sr ON sr.sr_reason_sk = r.r_reason_sk
)
SELECT
  ss.ss_customer_sk,
  SUM(
    CASE
      WHEN fr.sr_return_quantity IS NOT NULL
      THEN (ss.ss_quantity - fr.sr_return_quantity) * ss.ss_sales_price
      ELSE (ss.ss_quantity * ss.ss_sales_price)
    END
  ) AS sumsales
FROM filtered_returns fr
STRAIGHT_JOIN store_sales ss
  ON ss.ss_item_sk = fr.sr_item_sk
 AND ss.ss_ticket_number = fr.sr_ticket_number
WHERE ss.ss_customer_sk IS NOT NULL
GROUP BY ss.ss_customer_sk
ORDER BY sumsales, ss.ss_customer_sk
LIMIT 100;