/*
  Optimization procedure:
  1. Apply the exact 12-month date window and complete item category/class/
     brand disjunction in filtered CTEs.
  2. Drive from eligible item keys into store_sales, then use sold-date and
     store keys to retain only matching rows.
  3. Preserve manager/month grouping, the manager-partitioned window average,
     outer deviation predicate, ordering, and limit.

  All three item attributes remain correlated within each original OR branch;
  they are not converted into independent lists that would admit extra items.
*/
-- Law II: Restrict the date and item candidates before sales aggregation.
WITH filtered_dates AS (
    -- The source lists twelve consecutive month_seq values.
    SELECT d_date_sk, d_moy
    FROM date_dim
    WHERE d_month_seq BETWEEN 1176 AND 1187
),
filtered_items AS (
    -- Preserve the two complete item-predicate branches.
    SELECT i_item_sk, i_manager_id
    FROM item
    WHERE (i_category IN ('Books', 'Children', 'Electronics')
           AND i_class IN ('personal', 'portable', 'reference', 'self-help')
           AND i_brand IN ('scholaramalgamalg #14', 'scholaramalgamalg #7',
                           'exportiunivamalg #9', 'scholaramalgamalg #9'))
       OR (i_category IN ('Women', 'Music', 'Men')
           AND i_class IN ('accessories', 'classical', 'fragrances', 'pants')
           AND i_brand IN ('amalgimporto #1', 'edu packscholar #1',
                           'exportiimporto #1', 'importoamalg #1'))
),
monthly_sales AS (
    -- Law III: Probe sales from the filtered item key set.
    SELECT /*+ NO_MERGE(i) NO_MERGE(d) */
           i.i_manager_id,
           SUM(ss.ss_sales_price) AS sum_sales,
           AVG(SUM(ss.ss_sales_price))
               OVER (PARTITION BY i.i_manager_id) AS avg_monthly_sales
    FROM filtered_items i
    STRAIGHT_JOIN store_sales ss
        ON ss.ss_item_sk = i.i_item_sk
    STRAIGHT_JOIN filtered_dates d
        ON d.d_date_sk = ss.ss_sold_date_sk
    STRAIGHT_JOIN store s
        ON s.s_store_sk = ss.ss_store_sk
    -- Window input remains grouped at manager/month granularity.
    GROUP BY i.i_manager_id, d.d_moy
)
SELECT *
FROM monthly_sales tmp1
WHERE CASE WHEN avg_monthly_sales > 0
           THEN ABS(sum_sales - avg_monthly_sales) / avg_monthly_sales
           ELSE NULL END > 0.1
ORDER BY i_manager_id, avg_monthly_sales, sum_sales
LIMIT 100;
