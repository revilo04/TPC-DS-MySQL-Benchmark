WITH /*+ SET_VAR(tmp_table_size=1073741824) SET_VAR(max_heap_table_size=1073741824) */
filtered_dates AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_date BETWEEN CAST("2002-08-09" AS DATE)
                     AND (CAST("2002-08-09" AS DATE) + INTERVAL 30 DAY)
),
ss_agg AS (
    SELECT /*+ NO_MERGE() */
           ss.ss_store_sk,
           SUM(ss.ss_ext_sales_price) AS sales,
           SUM(COALESCE(sr.sr_return_amt, 0)) AS returns,
           SUM(ss.ss_net_profit - COALESCE(sr.sr_net_loss, 0)) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN store_sales ss ON ss.ss_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN item i ON ss.ss_item_sk = i.i_item_sk AND i.i_current_price > 50
    STRAIGHT_JOIN promotion p ON ss.ss_promo_sk = p.p_promo_sk AND p.p_channel_tv = "N"
    LEFT OUTER JOIN store_returns sr
      ON ss.ss_item_sk = sr.sr_item_sk AND ss.ss_ticket_number = sr.sr_ticket_number
    WHERE ss.ss_store_sk IS NOT NULL
    GROUP BY ss.ss_store_sk
),
ssr AS (
    SELECT s.s_store_id AS store_id,
           SUM(a.sales) AS sales,
           SUM(a.returns) AS returns,
           SUM(a.profit) AS profit
    FROM ss_agg a
    STRAIGHT_JOIN store s ON a.ss_store_sk = s.s_store_sk
    GROUP BY s.s_store_id
),
cs_agg AS (
    SELECT /*+ NO_MERGE() */
           cs.cs_catalog_page_sk,
           SUM(cs.cs_ext_sales_price) AS sales,
           SUM(COALESCE(cr.cr_return_amount, 0)) AS returns,
           SUM(cs.cs_net_profit - COALESCE(cr.cr_net_loss, 0)) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN catalog_sales cs ON cs.cs_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN item i ON cs.cs_item_sk = i.i_item_sk AND i.i_current_price > 50
    STRAIGHT_JOIN promotion p ON cs.cs_promo_sk = p.p_promo_sk AND p.p_channel_tv = "N"
    LEFT OUTER JOIN catalog_returns cr
      ON cs.cs_item_sk = cr.cr_item_sk AND cs.cs_order_number = cr.cr_order_number
    WHERE cs.cs_catalog_page_sk IS NOT NULL
    GROUP BY cs.cs_catalog_page_sk
),
csr AS (
    SELECT cp.cp_catalog_page_id AS catalog_page_id,
           SUM(a.sales) AS sales,
           SUM(a.returns) AS returns,
           SUM(a.profit) AS profit
    FROM cs_agg a
    STRAIGHT_JOIN catalog_page cp ON a.cs_catalog_page_sk = cp.cp_catalog_page_sk
    GROUP BY cp.cp_catalog_page_id
),
ws_agg AS (
    SELECT /*+ NO_MERGE() */
           ws.ws_web_site_sk,
           SUM(ws.ws_ext_sales_price) AS sales,
           SUM(COALESCE(wr.wr_return_amt, 0)) AS returns,
           SUM(ws.ws_net_profit - COALESCE(wr.wr_net_loss, 0)) AS profit
    FROM filtered_dates d
    STRAIGHT_JOIN web_sales ws ON ws.ws_sold_date_sk = d.d_date_sk
    STRAIGHT_JOIN item i ON ws.ws_item_sk = i.i_item_sk AND i.i_current_price > 50
    STRAIGHT_JOIN promotion p ON ws.ws_promo_sk = p.p_promo_sk AND p.p_channel_tv = "N"
    LEFT OUTER JOIN web_returns wr
      ON ws.ws_item_sk = wr.wr_item_sk AND ws.ws_order_number = wr.wr_order_number
    WHERE ws.ws_web_site_sk IS NOT NULL
    GROUP BY ws.ws_web_site_sk
),
wsr AS (
    SELECT web.web_site_id,
           SUM(a.sales) AS sales,
           SUM(a.returns) AS returns,
           SUM(a.profit) AS profit
    FROM ws_agg a
    STRAIGHT_JOIN web_site web ON a.ws_web_site_sk = web.web_site_sk
    GROUP BY web.web_site_id
)
SELECT channel,
       id,
       SUM(sales) AS sales,
       SUM(returns) AS returns,
       SUM(profit) AS profit
FROM (
    SELECT "store channel" AS channel, "store" || store_id AS id, sales, returns, profit FROM ssr
    UNION ALL
    SELECT "catalog channel" AS channel, "catalog_page" || catalog_page_id AS id, sales, returns, profit FROM csr
    UNION ALL
    SELECT "web channel" AS channel, "web_site" || web_site_id AS id, sales, returns, profit FROM wsr
) x
GROUP BY channel, id WITH ROLLUP
ORDER BY channel, id
LIMIT 100;
