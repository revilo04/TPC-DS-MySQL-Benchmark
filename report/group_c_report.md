# Group C Query Optimization Report

## Introduction

This report documents the Group C SQL revisions in [`queries/our_opt/`](../queries/our_opt/)
against the original benchmark statements in [`queries/qmod/`](../queries/qmod/).
The query grouping and optimization framework follow the Group C discussion in
[`TPC-DS_report.tex`](../TPC-DS_report.tex). The intent is to reduce avoidable
fact-table work and intermediate join cardinality while preserving every
baseline query's result semantics.

The authorized SF1 first-10 samples and `EXPLAIN ANALYZE` observations are
recorded in [`group_c_results.md`](group_c_results.md). The limited samples do
not establish full result equivalence, and the measured runtimes are single-run
observations rather than guarantees. No other scale factor is included.

## Optimization laws

### Law II: Selection pushdown and disjunctive bounding-box extraction

Apply selective filters as close as possible to the relation that owns the
filtered columns. Where an `OR` expression spans multiple relations, factor
common equijoin predicates out of the alternatives and prefilter each relation
to a safe superset of its branch domains. Keep the original branch correlations
as residual predicates whenever independent bounding-box conditions could
admit combinations that the original query excluded.

This rule also applies to date windows and local dimension filters: restricting
a date or dimension CTE before joining the large fact relation can reduce the
number of fact rows and dimension rows considered.

### Law III: Join associativity and deliberate physical join order

Inner joins can be associated in different orders without changing their
relational result, but intermediate row counts and access paths can differ
substantially. A filtered CTE with `NO_MERGE()` can retain a small filtered
dimension/date relation, while `STRAIGHT_JOIN` can request a join order that
starts from that restricted input and probes the fact table through its
foreign-key index.

These are physical-plan controls, not guarantees of a faster plan. Their
effectiveness depends on MySQL version, statistics, available indexes, data
distribution, and the actual plan. The execution-tree TODOs below are needed
to confirm the resulting plans.

## Group C definition and scope

The report defines Group C as queries susceptible to severe plan changes at
larger scale factors because filters are embedded in disjunctive predicates or
because the optimizer chooses an ineffective order for multi-table star
joins. Its intended remedies are Law II bounding-box/selection pushdown and
Law III materialized filtered dimensions with deliberate fact-table driving
order.

The Group C set is queries **7, 13, 19, 27, 36, 43, 46, 48, 53, 63, 73, 79,
and 89**. The corresponding optimized files are named `queryN_C.sql`.

## SF1 summary tables

### Summary metrics

| Query | Baseline cost | Baseline actual ms | Baseline rows | Optimized cost | Optimized actual ms | Optimized rows |
|---:|---:|---:|---:|---:|---:|---:|
| 7 | 253126 | 10063 | 100 | 153e+9 | 67325 | 100 |
| 13 | 324051 | 107374 | 1 | 725360 | 54804 | 1 |
| 19 | 372094 | 26.5 | 34 | 968e+6 | 9225 | 34 |
| 27 | 269663 | 9009 | 100 | 1.65e+9 | 92762 | 100 |
| 36 | 2.5..2.5 | 14728 | 100 | 2.5..2.5 | 65019 | 100 |
| 43 | 949175 | 39516 | 6 | 14.3e+6 | 51862 | 6 |
| 46 | 16214 | 104593 | 100 | 67.5e+6 | 44624 | 100 |
| 48 | 328074 | 101035 | 1 | 189699 | 54794 | 1 |
| 53 | 2.6..2.6 | 255 | 100 | 2.6..2.6 | 418 | 100 |
| 63 | 2.6..2.6 | 294 | 100 | 2.6..2.6 | 153 | 100 |
| 73 | 5362 | 51914 | 4 | 55.8e+6 | 13374 | 4 |
| 79 | 7433 | 30310 | 100 | 19.2e+6 | 25983 | 100 |
| 89 | 2.6..2.6 | 1783 | 100 | 2.6..2.6 | 58915 | 100 |

### Derived changes (baseline to optimized)

Time change is optimized minus baseline; negative values mean the optimized
query was faster. Cost change is the difference in estimated optimizer-cost
units, not elapsed time. Cost deltas and percentages are approximate where the
summary metrics above use rounded scientific notation.

| Query | Time change (ms) | Time change (%) | Cost change (optimizer units) | Cost change (%) |
|---:|---:|---:|---:|---:|
| 7 | +57262 | +569.04% | +152999746874 | +60444105.65% |
| 13 | -52570 | -48.96% | +401309 | +123.84% |
| 19 | +9198.5 | +34711.32% | +967627906 | +260049.32% |
| 27 | +83753 | +929.66% | +1649730337 | +611774.82% |
| 36 | +50291 | +341.47% | 0 | 0.00% |
| 43 | +12346 | +31.24% | +13350825 | +1406.57% |
| 46 | -59969 | -57.34% | +67483786 | +416206.90% |
| 48 | -46241 | -45.77% | -138375 | -42.18% |
| 53 | +163 | +63.92% | 0 | 0.00% |
| 63 | -141 | -47.96% | 0 | 0.00% |
| 73 | -38540 | -74.24% | +55794638 | +1040556.47% |
| 79 | -4327 | -14.28% | +19192567 | +258207.55% |
| 89 | +57132 | +3204.26% | 0 | 0.00% |

**Queries not optimized:** By estimated cost, all queries except Query 48 had
no cost reduction (Queries 36, 53, 63, and 89 were unchanged; the rest
increased). By elapsed time, Queries 7, 19, 27, 36, 43, 53, and 89 were slower.

## SF1 measurement snapshot

The single-run SF1 timings in [`group_c_results.md`](group_c_results.md) are
mixed: optimized elapsed time was lower for queries 13, 46, 48, 63, 73, and
79, and higher for queries 7, 19, 27, 36, 43, 53, and 89. These are individual
observations, not repeated benchmark averages. In particular, optimized Query
79 was rerun after a missing store-city projection was corrected, so that
measurement was not collected in the same immediate baseline/optimized pair
sequence. Compare the full trees and repeat runs before drawing general
performance conclusions.

## Summary of query optimizations

| Query | Main change | Laws / plan intent |
|---:|---|---|
| 7 | Filter 2002 dates, customer demographics, and promotion channels before joining; drive from dates. | II, III |
| 13 | Filter December 2001 dates and manager-94 items; drive from dates into sales, then resolve customer/address/store joins. | II, III |
| 19 | Same selective date and item-manager pushdown as Query 13; preserve the cross-relation ZIP-prefix comparison. | II, III |
| 27 | Filter 1999 dates, Tennessee stores, and customer demographics before grouping; retain `WITH ROLLUP`. | II, III |
| 36 | Filter 2001 dates and Tennessee stores before the sales join; retain rollup and window ranking. | II, III |
| 43 | Filter 2002 dates and stores with GMT offset -5 before aggregating sales by store and day name. | II, III |
| 46 | Filter the date range, store cities, and household-demographic OR condition before ticket aggregation; preserve grouping by address and bought city. | II, III |
| 48 | Prefilter 2002 dates, demographic/address candidates, and broad fact bounds; retain the original correlated branches. | II, III |
| 53 | Materialize the 12-month date window and full item category/class/brand disjunction; aggregate manufacturer sales by quarter. | II, III |
| 63 | Materialize the 12-month date window and full item disjunction; aggregate manager sales by month. | II, III |
| 73 | Filter the date, county-store, and household subsets before ticket/customer count aggregation. | II, III |
| 79 | Filter dates, employee-count stores, and the household OR before ticket totals. | II, III |
| 89 | Filter 2001 dates and the full item category/class disjunction before monthly store aggregation. | II, III |

## Query-by-query changes

### Query 7

- **Baseline:** [`queries/qmod/query7.sql`](../queries/qmod/query7.sql) joins
  sales to date, item, customer-demographic, and promotion dimensions, then
  applies year and dimension filters.
- **Optimized:** [`queries/our_opt/query7_C.sql`](../queries/our_opt/query7_C.sql)
  materializes the year-2002 dates, exact customer-demographic subset, and
  promotions satisfying the original email/event `OR`. It drives from dates
  into `store_sales` and joins the remaining dimensions by their surrogate
  keys.
- **Preserved behavior:** The full promotion `OR`, measures, averages, grouping,
  ordering, and limit are retained.

### Query 13

- **Baseline:** [`queries/qmod/query13.sql`](../queries/qmod/query13.sql) filters
  2001 store sales using two correlated disjunctions: three combinations of
  marital status, education, sales price, and household dependent count; and
  three combinations of address state and net-profit range.
- **Optimized:** [`queries/our_opt/query13_C.sql`](../queries/our_opt/query13_C.sql)
  materializes the year, household, demographic, and address filters, then
  drives from 2001 dates into sales. It adds inclusive fact-side bounds of
  50..200 for price and 50..300 for net profit before joining dimensions.
- **Preserved behavior and discrepancy:** All original branch correlations
  remain as residual predicates after applying the broad bounds. In
  particular, the actual baseline uses marital statuses `S`, `U`, and `W`,
  states `IA/MN/MT`, `AR/IN/TX`, and `TN/NE/WV`, and the original education and
  value ranges. The report's Query 13 walkthrough uses different constants;
  the checked-in `qmod` query is the source of truth.

### Query 19

- **Baseline:** [`queries/qmod/query19.sql`](../queries/qmod/query19.sql) filters
  December 2001 sales by item manager and compares the customer's current
  address ZIP prefix with the store ZIP prefix.
- **Optimized:** [`queries/our_opt/query19_C.sql`](../queries/our_opt/query19_C.sql)
  filters date and item inputs before joining sales, then looks up
  customer/address/store rows.
- **Preserved behavior:** The cross-relation `SUBSTR` inequality, aggregate,
  grouping attributes, sort keys, and limit remain in place. The inequality was
  not incorrectly converted into a one-table filter.

### Query 27

- **Baseline:** [`queries/qmod/query27.sql`](../queries/qmod/query27.sql) joins
  sales to dates, item, store, and customer demographics, applying a 1999 date
  filter, demographic filters, and repeated Tennessee state values.
- **Optimized:** [`queries/our_opt/query27_C.sql`](../queries/our_opt/query27_C.sql)
  pushes the date, state, and demographic filters into materialized CTEs and
  drives from the dates.
- **Preserved behavior:** Repeated `'TN'` entries in the baseline `IN` list
  collapse to the equivalent equality predicate. The grouping, `GROUPING()`,
  `WITH ROLLUP`, aggregates, ordering, and limit remain.

### Query 36

- **Baseline:** [`queries/qmod/query36.sql`](../queries/qmod/query36.sql) scans
  2001 sales and applies a repeated Tennessee state filter before category/class
  rollup and ranking.
- **Optimized:** [`queries/our_opt/query36_C.sql`](../queries/our_opt/query36_C.sql)
  restricts dates and stores first, then joins sales, item, and qualifying
  stores.
- **Preserved behavior:** The repeated state values are equivalent to
  `s_state = 'TN'`. The rollup, grouping-level calculation, rank window,
  ordering, and limit remain unchanged.

### Query 43

- **Baseline:** [`queries/qmod/query43.sql`](../queries/qmod/query43.sql) joins
  store sales with date and store and filters on year 2002 and GMT offset -5.
- **Optimized:** [`queries/our_opt/query43_C.sql`](../queries/our_opt/query43_C.sql)
  materializes those date/store subsets and drives sales from the selected
  dates. It carries `d_day_name` to the conditional aggregate.
- **Preserved behavior:** The seven `SUM(CASE...)` expressions, store grouping,
  output ordering, and limit are retained.

### Query 46

- **Baseline:** [`queries/qmod/query46.sql`](../queries/qmod/query46.sql) builds
  ticket-level totals from sales, dates, stores, household demographics, and
  the purchased address, then compares bought city with the customer's current
  address city.
- **Optimized:** [`queries/our_opt/query46_C.sql`](../queries/our_opt/query46_C.sql)
  materializes the date set and exact store/household filters before the
  ticket-level aggregation; customer/current-address lookup remains after that
  aggregation.
- **Preserved behavior:** Repeated city entries reduce to
  `s_city IN ('Fairview', 'Midway')`. The inner grouping still includes
  `ss_addr_sk` and purchased city, and the outer city inequality and sort keys
  remain.

### Query 48

- **Baseline:** [`queries/qmod/query48.sql`](../queries/qmod/query48.sql) sums
  `ss_quantity` for year 2002 using three correlated demographic/price
  branches and three address/state/profit branches.
- **Optimized:** [`queries/our_opt/query48_C.sql`](../queries/our_opt/query48_C.sql)
  prefilters year, exact demographic/address candidate sets, and safe outer
  fact ranges before joining store and the filtered dimensions.
- **Preserved behavior:** All original branch-specific pairings and ranges
  remain in the final predicate. Bounds are supersets only; no grouping or
  aggregation is introduced.

### Query 53

- **Baseline:** [`queries/qmod/query53.sql`](../queries/qmod/query53.sql) applies
  a 12-month window and two correlated item category/class/brand branches,
  grouping sales by manufacturer and quarter with a window average.
- **Optimized:** [`queries/our_opt/query53_C.sql`](../queries/our_opt/query53_C.sql)
  materializes the exact date and item subsets, drives sales from qualifying
  item keys, and retains the baseline store join.
- **Preserved behavior:** Manufacturer/quarter grouping,
  manufacturer-partitioned `AVG(SUM(...))`, deviation predicate, ordering, and
  limit remain.

### Query 63

- **Baseline:** [`queries/qmod/query63.sql`](../queries/qmod/query63.sql) applies
  a 12-month window and two correlated item category/class/brand branches,
  grouping sales by manager and month.
- **Optimized:** [`queries/our_opt/query63_C.sql`](../queries/our_opt/query63_C.sql)
  materializes the exact item and date subsets, drives from qualifying item
  keys into sales, and retains the store join.
- **Preserved behavior:** Manager/month grouping, manager-partitioned window
  average, deviation predicate, ordering, and limit remain.

### Query 73

- **Baseline:** [`queries/qmod/query73.sql`](../queries/qmod/query73.sql) counts
  tickets after filtering date-of-month/year, Williamson County stores, and
  household buy-potential/vehicle/dependent conditions.
- **Optimized:** [`queries/our_opt/query73_C.sql`](../queries/our_opt/query73_C.sql)
  pushes those exact filters into date, store, and household CTEs; it retains
  ticket/customer grouping and joins customer afterward.
- **Preserved behavior:** The household ratio `CASE`, `cnt BETWEEN 1 AND 5`,
  output columns, and ordering remain; the baseline has no limit.

### Query 79

- **Baseline:** [`queries/qmod/query79.sql`](../queries/qmod/query79.sql) builds
  ticket-level coupon/profit totals for weekday sales from 1999â€“2001, qualifying
  stores and a household OR condition.
- **Optimized:** [`queries/our_opt/query79_C.sql`](../queries/our_opt/query79_C.sql)
  materializes those date/store/household subsets and drives sales from dates.
- **Preserved behavior:** `ss_addr_sk` remains in the inner grouping, the
  customer join stays after aggregation, and the city substring, ordering, and
  limit remain. The broad `hd_vehicle_count > -1` disjunct is retained
  verbatim, including its NULL behavior.

### Query 89

- **Baseline:** [`queries/qmod/query89.sql`](../queries/qmod/query89.sql) filters
  2001 sales using two item category/class branches and groups by item and
  store attributes/month before applying a window average.
- **Optimized:** [`queries/our_opt/query89_C.sql`](../queries/our_opt/query89_C.sql)
  materializes the date and full correlated item filter before joining sales,
  while retaining the store relation.
- **Preserved behavior:** Grouping, window partition, deviation condition,
  ordering, and limit remain.

## Issues, challenges, and open questions

1. **Result equivalence is not established:** SF1 sample rows and full-query
   `EXPLAIN ANALYZE` executions are recorded in
   [`group_c_results.md`](group_c_results.md), but a ten-row sample cannot
   prove that every result row matches.
2. **Query 13 source/report mismatch:** The report's example predicates differ
   from the actual baseline. This revision follows `qmod`; confirm the report
   example independently before using it as a benchmark reference.
3. **Hints and forced order:** The captured plans show the plans chosen on this
   MySQL instance, but `NO_MERGE()` and `STRAIGHT_JOIN` can produce different
   outcomes with different versions, statistics, indexes, or data. Forcing an
   order can regress performance if a different path is more selective.
4. **Potential data-domain assumptions:** Query 79's household predicate was
   left intact rather than relying on presumed nonnegative vehicle counts.
   Similar domain-based simplifications should be avoided unless the schema and
   data constraints justify them.
5. **Rollup/window behavior:** Queries 27 and 36 completed `EXPLAIN ANALYZE`
   on this target MySQL instance. Their full result sets have not been compared
   with the baseline.
6. **Single-run measurements:** Costs and runtimes in the results file are
   single-run observations, not repeatable benchmark averages. Optimized Query
   79 was rerun after fixing a missing `s_city` projection in its filtered
   store CTE; its timing was collected separately from its baseline run.

## Execution trees and remaining result check

The complete baseline and optimized `EXPLAIN ANALYZE` trees and root metrics
for all 13 pairs are recorded in
[`group_c_results.md`](group_c_results.md). The execution trees are captured
from the SF1 database; no plan text is fabricated.

- [ ] In a later database validation, compare full baseline and optimized result
      sets for all 13 queries before claiming result equivalence.
