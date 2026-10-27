WITH d_months AS (
    SELECT /*+ NO_MERGE() */ d_date_sk, d_year, d_moy
    FROM date_dim
    WHERE d_year = 2001
       OR (d_year = 2001 - 1 AND d_moy = 12)
       OR (d_year = 2001 + 1 AND d_moy = 1)
),
-- Map the non-unique (category, brand) and (store name, company name) pairs to small integer
-- group ids so store_sales is aggregated once on integer keys. NULL pairs are dropped: the
-- original lag/lead equality self-joins never match them.
item_groups AS (
    SELECT /*+ NO_MERGE() */
           i_item_sk,
           i_category,
           i_brand,
           DENSE_RANK() OVER (ORDER BY i_category, i_brand) AS item_grp
    FROM item
    WHERE i_category IS NOT NULL
      AND i_brand IS NOT NULL
),
store_groups AS (
    SELECT /*+ NO_MERGE() */
           s_store_sk,
           s_store_name,
           s_company_name,
           DENSE_RANK() OVER (ORDER BY s_store_name, s_company_name) AS store_grp
    FROM store
    WHERE s_store_name IS NOT NULL
      AND s_company_name IS NOT NULL
),
monthly AS (
    SELECT /*+ NO_MERGE() */
           ig.item_grp,
           sg.store_grp,
           d.d_year,
           d.d_moy,
           SUM(ss.ss_sales_price) AS sum_sales
    FROM d_months d
    STRAIGHT_JOIN store_sales ss
      ON ss.ss_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN item_groups ig
      ON ig.i_item_sk = ss.ss_item_sk
    STRAIGHT_JOIN store_groups sg
      ON sg.s_store_sk = ss.ss_store_sk
    GROUP BY ig.item_grp, sg.store_grp, d.d_year, d.d_moy
),
v1 AS (
    SELECT item_grp,
           store_grp,
           d_year,
           d_moy,
           sum_sales,
           AVG(sum_sales) OVER (PARTITION BY item_grp, store_grp, d_year) AS avg_monthly_sales,
           RANK() OVER (PARTITION BY item_grp, store_grp ORDER BY d_year, d_moy) AS rn
    FROM monthly
),
-- LAG/LEAD replace the original lag/lead self-joins (rn has no ties within a partition)
v2 AS (
    SELECT store_grp,
           d_year,
           d_moy,
           avg_monthly_sales,
           sum_sales,
           LAG(sum_sales) OVER w AS psum,
           LEAD(sum_sales) OVER w AS nsum,
           rn,
           LAG(rn) OVER w AS prev_rn,
           LEAD(rn) OVER w AS next_rn
    FROM v1
    WINDOW w AS (PARTITION BY item_grp, store_grp ORDER BY rn)
),
store_names AS (
    SELECT store_grp, MIN(s_company_name) AS s_company_name
    FROM store_groups
    GROUP BY store_grp
)
SELECT sn.s_company_name,
       v2.d_year,
       v2.d_moy,
       v2.avg_monthly_sales,
       v2.sum_sales,
       v2.psum,
       v2.nsum
FROM v2
STRAIGHT_JOIN store_names sn
  ON sn.store_grp = v2.store_grp
WHERE v2.prev_rn = v2.rn - 1
  AND v2.next_rn = v2.rn + 1
  AND v2.d_year = 2001
  AND v2.avg_monthly_sales > 0
  AND CASE WHEN v2.avg_monthly_sales > 0 THEN ABS(v2.sum_sales - v2.avg_monthly_sales) / v2.avg_monthly_sales ELSE NULL END > 0.1
ORDER BY v2.sum_sales - v2.avg_monthly_sales, v2.psum
LIMIT 100;
