WITH d_window AS (
    SELECT /*+ NO_MERGE() */ d_date_sk, d_date
    FROM date_dim
    WHERE d_date BETWEEN (CAST('2002-03-20' AS DATE) - INTERVAL 30 DAY)
                     AND (CAST('2002-03-20' AS DATE) + INTERVAL 30 DAY)
),
priced_items AS (
    SELECT /*+ NO_MERGE() */ i_item_sk, i_item_id
    FROM item
    WHERE i_current_price BETWEEN 0.99 AND 1.49
),
-- Range scan on the inventory primary key prefix (inv_date_sk), aggregated by integer keys
inv_totals AS (
    SELECT /*+ NO_MERGE() */
           inv.inv_warehouse_sk,
           inv.inv_item_sk,
           SUM(CASE WHEN CAST(d.d_date AS DATE) < CAST('2002-03-20' AS DATE)
                    THEN inv.inv_quantity_on_hand ELSE 0 END) AS inv_before,
           SUM(CASE WHEN CAST(d.d_date AS DATE) >= CAST('2002-03-20' AS DATE)
                    THEN inv.inv_quantity_on_hand ELSE 0 END) AS inv_after
    FROM d_window d
    STRAIGHT_JOIN inventory inv
      ON inv.inv_date_sk = d.d_date_sk
    WHERE inv.inv_item_sk IN (SELECT i_item_sk FROM priced_items)
    GROUP BY inv.inv_warehouse_sk, inv.inv_item_sk
)
SELECT *
FROM (
    -- w_warehouse_name and i_item_id are not unique per surrogate key: aggregate again
    SELECT w.w_warehouse_name,
           i.i_item_id,
           SUM(t.inv_before) AS inv_before,
           SUM(t.inv_after) AS inv_after
    FROM inv_totals t
    STRAIGHT_JOIN warehouse w
      ON w.w_warehouse_sk = t.inv_warehouse_sk
    STRAIGHT_JOIN priced_items i
      ON i.i_item_sk = t.inv_item_sk
    GROUP BY w.w_warehouse_name, i.i_item_id
) x
WHERE (CASE WHEN inv_before > 0
            THEN inv_after / inv_before
            ELSE NULL
            END) BETWEEN 2.0 / 3.0 AND 3.0 / 2.0
ORDER BY w_warehouse_name,
         i_item_id
LIMIT 100;
