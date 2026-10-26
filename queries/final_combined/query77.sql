WITH /*+ SET_VAR(tmp_table_size=1073741824) SET_VAR(max_heap_table_size=1073741824) */
filtered_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_date BETWEEN CAST("2002-08-09" AS DATE)
                     AND (CAST("2002-08-09" AS DATE) + INTERVAL 30 DAY)
),
ss AS (
    SELECT /*+ NO_MERGE() */
           s.s_store_sk,
           SUM(ss.ss_ext_sales_price) AS sales,
           SUM(ss.ss_net_profit) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN store s ON ss.ss_store_sk = s.s_store_sk
    GROUP BY s.s_store_sk
),
sr AS (
    SELECT /*+ NO_MERGE() */
           s.s_store_sk,
           SUM(sr.sr_return_amt) AS returns,
           SUM(sr.sr_net_loss) AS profit_loss
    FROM filtered_dates d
    STRAIGHT_JOIN store_returns sr ON sr.sr_returned_date_sk = d.d_date_sk
    STRAIGHT_JOIN store s ON sr.sr_store_sk = s.s_store_sk
    GROUP BY s.s_store_sk
),
cs AS (
    SELECT /*+ NO_MERGE() */
           cs.cs_call_center_sk,
           SUM(cs.cs_ext_sales_price) AS sales,
           SUM(cs.cs_net_profit) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN catalog_sales cs ON cs.cs_sold_date_sk = d.d_date_sk
    GROUP BY cs.cs_call_center_sk
),
cr AS (
    SELECT /*+ NO_MERGE() */
           cr.cr_call_center_sk,
           SUM(cr.cr_return_amount) AS returns,
           SUM(cr.cr_net_loss) AS profit_loss
    FROM filtered_dates d
    STRAIGHT_JOIN catalog_returns cr ON cr.cr_returned_date_sk = d.d_date_sk
    GROUP BY cr.cr_call_center_sk
),
ws AS (
    SELECT /*+ NO_MERGE() */
           wp.wp_web_page_sk,
           SUM(ws.ws_ext_sales_price) AS sales,
           SUM(ws.ws_net_profit) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN web_page wp ON ws.ws_web_page_sk = wp.wp_web_page_sk
    GROUP BY wp.wp_web_page_sk
),
wr AS (
    SELECT /*+ NO_MERGE() */
           wp.wp_web_page_sk,
           SUM(wr.wr_return_amt) AS returns,
           SUM(wr.wr_net_loss) AS profit_loss
    FROM filtered_dates d
    STRAIGHT_JOIN web_returns wr ON wr.wr_returned_date_sk = d.d_date_sk
    STRAIGHT_JOIN web_page wp ON wr.wr_web_page_sk = wp.wp_web_page_sk
    GROUP BY wp.wp_web_page_sk
)
SELECT channel,
       id,
       SUM(sales) AS sales,
       SUM(returns) AS returns,
       SUM(profit) AS profit
FROM (
    SELECT "store channel" AS channel,
           ss.s_store_sk AS id,
           sales,
           COALESCE(returns, 0) AS returns,
           (profit - COALESCE(profit_loss, 0)) AS profit
    FROM ss LEFT JOIN sr ON ss.s_store_sk = sr.s_store_sk
    UNION ALL
    SELECT "catalog channel" AS channel,
           cs_call_center_sk AS id,
           sales,
           returns,
           (profit - profit_loss) AS profit
    FROM cs, cr
    UNION ALL
    SELECT "web channel" AS channel,
           ws.wp_web_page_sk AS id,
           sales,
           COALESCE(returns, 0) AS returns,
           (profit - COALESCE(profit_loss, 0)) AS profit
    FROM ws LEFT JOIN wr ON ws.wp_web_page_sk = wr.wp_web_page_sk
) x
GROUP BY channel, id WITH ROLLUP
ORDER BY channel, id
LIMIT 100;
