WITH d_aug_2001 AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_year = 2001
      AND d_moy = 8
),
-- Drive from one month of returns into store_sales via its (ss_item_sk, ss_ticket_number)
-- primary key and count by the integer store key before reading store attributes
returns_by_store AS (
    SELECT /*+ NO_MERGE() */
           ss.ss_store_sk,
           SUM(CASE WHEN (sr.sr_returned_date_sk - ss.ss_sold_date_sk <= 30) THEN 1 ELSE 0 END) AS days_30,
           SUM(CASE WHEN (sr.sr_returned_date_sk - ss.ss_sold_date_sk > 30)
                     AND (sr.sr_returned_date_sk - ss.ss_sold_date_sk <= 60) THEN 1 ELSE 0 END) AS days_31_60,
           SUM(CASE WHEN (sr.sr_returned_date_sk - ss.ss_sold_date_sk > 60)
                     AND (sr.sr_returned_date_sk - ss.ss_sold_date_sk <= 90) THEN 1 ELSE 0 END) AS days_61_90,
           SUM(CASE WHEN (sr.sr_returned_date_sk - ss.ss_sold_date_sk > 90)
                     AND (sr.sr_returned_date_sk - ss.ss_sold_date_sk <= 120) THEN 1 ELSE 0 END) AS days_91_120,
           SUM(CASE WHEN (sr.sr_returned_date_sk - ss.ss_sold_date_sk > 120) THEN 1 ELSE 0 END) AS days_over_120
    FROM d_aug_2001 d2
    STRAIGHT_JOIN store_returns sr
      ON sr.sr_returned_date_sk = d2.d_date_sk
    STRAIGHT_JOIN store_sales ss
      ON ss.ss_item_sk = sr.sr_item_sk
     AND ss.ss_ticket_number = sr.sr_ticket_number
     AND ss.ss_customer_sk = sr.sr_customer_sk
    STRAIGHT_JOIN date_dim d1
      ON d1.d_date_sk = ss.ss_sold_date_sk
    GROUP BY ss.ss_store_sk
)
-- Store attributes are not unique per s_store_sk: aggregate again
SELECT s.s_store_name,
       s.s_company_id,
       s.s_street_number,
       s.s_street_name,
       s.s_street_type,
       s.s_suite_number,
       s.s_city,
       s.s_county,
       s.s_state,
       s.s_zip,
       SUM(r.days_30) AS "30 days",
       SUM(r.days_31_60) AS "31-60 days",
       SUM(r.days_61_90) AS "61-90 days",
       SUM(r.days_91_120) AS "91-120 days",
       SUM(r.days_over_120) AS ">120 days"
FROM returns_by_store r
STRAIGHT_JOIN store s
  ON s.s_store_sk = r.ss_store_sk
GROUP BY s.s_store_name,
         s.s_company_id,
         s.s_street_number,
         s.s_street_name,
         s.s_street_type,
         s.s_suite_number,
         s.s_city,
         s.s_county,
         s.s_state,
         s.s_zip
ORDER BY s.s_store_name,
         s.s_company_id,
         s.s_street_number,
         s.s_street_name,
         s.s_street_type,
         s.s_suite_number,
         s.s_city,
         s.s_county,
         s.s_state,
         s.s_zip
LIMIT 100;
