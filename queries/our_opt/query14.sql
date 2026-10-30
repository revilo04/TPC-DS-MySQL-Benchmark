WITH cross_items AS (
    SELECT iss.i_item_sk AS ss_item_sk
    FROM item iss
    JOIN store_sales ON ss_item_sk = iss.i_item_sk
    JOIN date_dim d1 ON ss_sold_date_sk = d1.d_date_sk AND d1.d_year BETWEEN 1999 AND 2001
    INTERSECT
    SELECT ics.i_item_sk
    FROM item ics
    JOIN catalog_sales ON cs_item_sk = ics.i_item_sk
    JOIN date_dim d2 ON cs_sold_date_sk = d2.d_date_sk AND d2.d_year BETWEEN 1999 AND 2001
    INTERSECT
    SELECT iws.i_item_sk
    FROM item iws
    JOIN web_sales ON ws_item_sk = iws.i_item_sk
    JOIN date_dim d3 ON ws_sold_date_sk = d3.d_date_sk AND d3.d_year BETWEEN 1999 AND 2001
),
avg_sales AS (
    SELECT avg(quantity * list_price) AS average_sales
    FROM (
        SELECT ss_quantity AS quantity, ss_list_price AS list_price
        FROM store_sales
        JOIN date_dim ON ss_sold_date_sk = d_date_sk AND d_year BETWEEN 1999 AND 2001
        UNION ALL
        SELECT cs_quantity, cs_list_price
        FROM catalog_sales
        JOIN date_dim ON cs_sold_date_sk = d_date_sk AND d_year BETWEEN 1999 AND 2001
        UNION ALL
        SELECT ws_quantity, ws_list_price
        FROM web_sales
        JOIN date_dim ON ws_sold_date_sk = d_date_sk AND d_year BETWEEN 1999 AND 2001
    ) x
)
SELECT 
    channel,
    i_brand_id,
    i_class_id,
    i_category_id,
    sum(sales),
    sum(number_sales)
FROM (
    SELECT 
        'store' AS channel,
        i_brand_id,
        i_class_id,
        i_category_id,
        sum(ss_quantity * ss_list_price) AS sales,
        count(*) AS number_sales
    FROM store_sales
    JOIN cross_items ON ss_item_sk = cross_items.ss_item_sk
    JOIN item ON ss_item_sk = item.i_item_sk
    JOIN date_dim ON ss_sold_date_sk = d_date_sk AND d_year = 2001 AND d_moy = 11
    GROUP BY i_brand_id, i_class_id, i_category_id
    HAVING sum(ss_quantity * ss_list_price) > (SELECT average_sales FROM avg_sales)
    
    UNION ALL
    
    SELECT 
        'catalog' AS channel,
        i_brand_id,
        i_class_id,
        i_category_id,
        sum(cs_quantity * cs_list_price) AS sales,
        count(*) AS number_sales
    FROM catalog_sales
    JOIN cross_items ON cs_item_sk = cross_items.ss_item_sk
    JOIN item ON cs_item_sk = item.i_item_sk
    JOIN date_dim ON cs_sold_date_sk = d_date_sk AND d_year = 2001 AND d_moy = 11
    GROUP BY i_brand_id, i_class_id, i_category_id
    HAVING sum(cs_quantity * ss_list_price) > (SELECT average_sales FROM avg_sales)
    
    UNION ALL
    
    SELECT 
        'web' AS channel,
        i_brand_id,
        i_class_id,
        i_category_id,
        sum(ws_quantity * ws_list_price) AS sales,
        count(*) AS number_sales
    FROM web_sales
    JOIN cross_items ON ws_item_sk = cross_items.ss_item_sk
    JOIN item ON ws_item_sk = item.i_item_sk
    JOIN date_dim ON ws_sold_date_sk = d_date_sk AND d_year = 2001 AND d_moy = 11
    GROUP BY i_brand_id, i_class_id, i_category_id
    HAVING sum(ws_quantity * ss_list_price) > (SELECT average_sales FROM avg_sales)
) y
GROUP BY channel, i_brand_id, i_class_id, i_category_id WITH ROLLUP
ORDER BY channel, i_brand_id, i_class_id, i_category_id
LIMIT 100;