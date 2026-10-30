WITH DateRange AS (
    SELECT d_date_sk 
    FROM date_dim 
    WHERE d_date BETWEEN '2002-08-09' AND DATE_ADD('2002-08-09', INTERVAL 14 DAY)
),
SSR AS (
    SELECT 
        s_store_id,
        SUM(CASE WHEN salesreturns.source = 'SALES' THEN sales_price ELSE 0 END) AS sales,
        SUM(CASE WHEN salesreturns.source = 'SALES' THEN profit ELSE 0 END) - SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN net_loss ELSE 0 END) AS profit,
        SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN return_amt ELSE 0 END) AS returns,
        SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN net_loss ELSE 0 END) AS profit_loss
    FROM (
        SELECT 
            'SALES' AS source,
            ss_store_sk AS store_sk,
            ss_ext_sales_price AS sales_price,
            ss_net_profit AS profit,
            0 AS return_amt,
            0 AS net_loss
        FROM store_sales
        JOIN DateRange ON ss_sold_date_sk = d_date_sk
        UNION ALL
        SELECT 
            'RETURNS' AS source,
            sr_store_sk AS store_sk,
            0 AS sales_price,
            0 AS profit,
            sr_return_amt AS return_amt,
            sr_net_loss AS net_loss
        FROM store_returns
        JOIN DateRange ON sr_returned_date_sk = d_date_sk
    ) AS salesreturns
    JOIN store ON salesreturns.store_sk = store.s_store_sk
    GROUP BY s_store_id
),
CSR AS (
    SELECT 
        cp_catalog_page_id,
        SUM(CASE WHEN salesreturns.source = 'SALES' THEN sales_price ELSE 0 END) AS sales,
        SUM(CASE WHEN salesreturns.source = 'SALES' THEN profit ELSE 0 END) - SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN net_loss ELSE 0 END) AS profit,
        SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN return_amt ELSE 0 END) AS returns,
        SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN net_loss ELSE 0 END) AS profit_loss
    FROM (
        SELECT 
            'SALES' AS source,
            cs_catalog_page_sk AS page_sk,
            cs_ext_sales_price AS sales_price,
            cs_net_profit AS profit,
            0 AS return_amt,
            0 AS net_loss
        FROM catalog_sales
        JOIN DateRange ON cs_sold_date_sk = d_date_sk
        UNION ALL
        SELECT 
            'RETURNS' AS source,
            cr_catalog_page_sk AS page_sk,
            0 AS sales_price,
            0 AS profit,
            cr_catalog_page_id AS return_amt, -- adjusted mapping
            cr_net_loss AS net_loss
        FROM catalog_returns
        JOIN DateRange ON cr_returned_date_sk = d_date_sk
    ) AS salesreturns
    JOIN catalog_page ON salesreturns.page_sk = catalog_page.cp_catalog_page_sk
    GROUP BY cp_catalog_page_id
),
WSR AS (
    SELECT 
        web_site_id,
        SUM(CASE WHEN salesreturns.source = 'SALES' THEN sales_price ELSE 0 END) AS sales,
        SUM(CASE WHEN salesreturns.source = 'SALES' THEN profit ELSE 0 END) - SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN net_loss ELSE 0 END) AS profit,
        SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN return_amt ELSE 0 END) AS returns,
        SUM(CASE WHEN salesreturns.source = 'RETURNS' THEN net_loss ELSE 0 END) AS profit_loss
    FROM (
        SELECT 
            'SALES' AS source,
            ws_web_site_sk AS wsr_web_site_sk,
            ws_ext_sales_price AS sales_price,
            ws_net_profit AS profit,
            0 AS return_amt,
            0 AS net_loss
        FROM web_sales
        JOIN DateRange ON ws_sold_date_sk = d_date_sk
        UNION ALL
        SELECT 
            'RETURNS' AS source,
            ws.ws_web_site_sk AS wsr_web_site_sk,
            0 AS sales_price,
            0 AS profit,
            wr_return_amt AS return_amt,
            wr_net_loss AS net_loss
        FROM web_returns
        JOIN web_sales ws ON wr_item_sk = ws.ws_item_sk AND wr_order_number = ws.ws_order_number
        JOIN DateRange ON wr_returned_date_sk = d_date_sk
    ) AS salesreturns
    JOIN web_site ON salesreturns.wsr_web_site_sk = web_site.web_site_sk
    GROUP BY web_site_id
)
SELECT 
    channel,
    id,
    SUM(sales) AS sales,
    SUM(returns) AS returns,
    SUM(profit) AS profit
FROM (
    SELECT 'STORE CHANNEL' AS channel, CONCAT('STORE', s_store_id) AS id, sales, returns, profit FROM SSR
    UNION ALL
    SELECT 'CATALOG CHANNEL' AS channel, CONCAT('CATALOG_PAGE', cp_catalog_page_id) AS id, sales, returns, profit FROM CSR
    UNION ALL
    SELECT 'WEB CHANNEL' AS channel, CONCAT('WEB_SITE', web_site_id) AS id, sales, returns, profit FROM WSR
) x
GROUP BY channel, id WITH ROLLUP
ORDER BY channel, id
LIMIT 100;