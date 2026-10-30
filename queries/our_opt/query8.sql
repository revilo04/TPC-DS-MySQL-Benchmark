SELECT s_store_name, sum(ss_net_profit)
FROM store_sales
JOIN date_dim ON ss_sold_date_sk = d_date_sk AND d_qoy = 2 AND d_year = 2002
JOIN store ON ss_store_sk = s_store_sk
JOIN (
    SELECT DISTINCT ca_zip
    FROM (
        SELECT substr(ca_zip, 1, 5) AS ca_zip
        FROM customer_address
    ) t1
    INNER JOIN (
        SELECT substr(ca_zip, 1, 5) AS ca_zip
        FROM customer_address ca
        JOIN customer c ON ca.ca_address_sk = c.c_current_addr_sk
        WHERE c.c_preferred_cust_flag = 'Y'
        GROUP BY substr(ca_zip, 1, 5)
        HAVING count(*) > 10
    ) t2 ON t1.ca_zip = t2.ca_zip
) V1 ON substr(s_zip, 1, 2) = substr(V1.ca_zip, 1, 2)
group by s_store_name
order by s_store_name
limit 100;