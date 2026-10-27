WITH d_2002 AS (
    SELECT /*+ NO_MERGE() */ d_date_sk
    FROM date_dim
    WHERE d_year = 2002
),
customer_total_return AS (
    SELECT /*+ NO_MERGE() */
           cr.cr_returning_customer_sk AS ctr_customer_sk,
           ca.ca_state AS ctr_state,
           SUM(cr.cr_return_amt_inc_tax) AS ctr_total_return
    FROM d_2002 d
    STRAIGHT_JOIN catalog_returns cr
      ON cr.cr_returned_date_sk = d.d_date_sk
    STRAIGHT_JOIN customer_address ca
      ON ca.ca_address_sk = cr.cr_returning_addr_sk
    GROUP BY cr.cr_returning_customer_sk, ca.ca_state
),
-- Decorrelated per-state threshold, computed once instead of once per outer row.
-- A NULL ctr_state never satisfies the join, as in the original correlated predicate.
state_threshold AS (
    SELECT /*+ NO_MERGE() */
           ctr_state,
           AVG(ctr_total_return) * 1.2 AS threshold
    FROM customer_total_return
    GROUP BY ctr_state
)
SELECT c.c_customer_id, c.c_salutation, c.c_first_name, c.c_last_name,
       ca.ca_street_number, ca.ca_street_name, ca.ca_street_type, ca.ca_suite_number,
       ca.ca_city, ca.ca_county, ca.ca_state, ca.ca_zip, ca.ca_country, ca.ca_gmt_offset,
       ca.ca_location_type, ctr1.ctr_total_return
FROM customer_total_return ctr1
STRAIGHT_JOIN state_threshold st
  ON st.ctr_state = ctr1.ctr_state
STRAIGHT_JOIN customer c
  ON c.c_customer_sk = ctr1.ctr_customer_sk
STRAIGHT_JOIN customer_address ca
  ON ca.ca_address_sk = c.c_current_addr_sk
WHERE ctr1.ctr_total_return > st.threshold
  AND ca.ca_state = 'NH'
ORDER BY c.c_customer_id, c.c_salutation, c.c_first_name, c.c_last_name,
         ca.ca_street_number, ca.ca_street_name, ca.ca_street_type, ca.ca_suite_number,
         ca.ca_city, ca.ca_county, ca.ca_state, ca.ca_zip, ca.ca_country, ca.ca_gmt_offset,
         ca.ca_location_type, ctr1.ctr_total_return
LIMIT 100;
