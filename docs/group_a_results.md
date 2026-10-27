# Group A Optimization Results (Q4, Q11, Q21, Q47, Q50, Q74, Q81)

> Date: 2026-10-26. Optimized SQL: `queries/our_opt/query<n>.sql` (synced to `queries/final_combined/`).

## 1. Environment and Method

- **Machine**: Apple M4 (10 cores), 24 GiB RAM, MySQL 8.4.13, `innodb_buffer_pool_size` 6 GiB (2 instances). The full configuration of every run is in its `_meta.json`.
- **Data**: SF1 (`tpcds`, 4.34 GB) and SF2 (`tpcds2`, 7.59 GB, larger than the buffer pool). Both were generated with seed 19620718 and their row counts were checked table by table against the generated files.
- **Baseline**: `queries/qmod_combined/`, with Q4 and Q11 restored to their original semantics (commit "fix: restore original semantics of baseline Q4 and Q11", see Section 4).
- **Correctness**: `python -m scripts.compare_results --sf <sf> --base queries/qmod_combined --cand queries/our_opt --query <n> --no-limit`. This drops the trailing `LIMIT` and compares complete result sets: Decimal and text values must match exactly, floats within a relative tolerance of 1e-9. **All seven queries match on SF1 and SF2**, including row order (no `order-only` differences).
- **Timing**: `python -m scripts.power_test --qdir <dir> --query ... --warmup --timeout 900`, three runs per configuration, median reported. Timings include fetching all rows. All 12 runs succeeded. Across the three runs of a query, max/min was at most 1.51 (baseline) and 1.15 (optimized).

## 2. Results (median of 3 runs, seconds)

| Query | SF1 baseline | SF1 optimized | SF1 speedup | SF2 baseline | SF2 optimized | SF2 speedup |
|---|---:|---:|---:|---:|---:|---:|
| Q4 | 50.954 | 3.053 | 16.7x | 112.460 | 5.821 | 19.3x |
| Q11 | 35.522 | 2.128 | 16.7x | 71.957 | 4.150 | 17.3x |
| Q21 | 0.337 | 0.142 | 2.4x | 25.189 | 0.189 | **133.1x** |
| Q47 | 9.365 | 1.884 | 5.0x | 18.915 | 3.219 | 5.9x |
| Q50 | 0.032 | 0.023 | 1.4x | 0.050 | 0.032 | 1.6x |
| Q74 | 11.797 | 2.048 | 5.8x | 25.602 | 3.923 | 6.5x |
| Q81 | 1.981 | 0.098 | 20.3x | 7.012 | 0.175 | 40.0x |
| **Total** | **110.0** | **9.4** | **11.7x** | **261.2** | **17.5** | **14.9x** |

- Raw data: `results/pt_sf={1,2}_10-26_*_q4-11-21-47-50-74-81.txt` and the matching `_meta.json` files.
- Execution plans: `results/explain/sf{1,2}/{qmod_combined,our_opt}/query<n>.txt`.
- From SF1 to SF2 the baseline total grows 2.37x and the optimized total 1.86x.

## 3. Bottleneck, Rewrite and Equivalence per Query

### Q4 / Q11 / Q74: year pivot (Law I + Law III)

- **Bottleneck**: the `year_total` CTE is aggregated and materialized by (seven customer string columns, year), over **all years** in Q4 and Q11, and then self-joined four times (six in Q4) on the string `customer_id`. On SF1 the baseline drives from `customer` through `ss_c` and reads all of `store_sales`.
- **Rewrite**:
  - Each sales channel is scanned once, driven from a `date_dim` CTE restricted to the two target years through the `ss_d` / `ws_d2` / `cs_d2` indexes (Law III).
  - Rows are grouped by the integer `customer_sk`, computing both years at once with `SUM(CASE WHEN d_year = y THEN expr END)` (Law I).
  - Channels are joined on `customer_sk`, and `customer` is joined once at the end for the output columns.
- **Equivalence**:
  - `c_customer_id` is unique on SF1 and SF2, so grouping by the surrogate key equals grouping by the id and its attributes.
  - The `CASE` has no `ELSE` (i.e. `ELSE NULL`), so a year whose values are all NULL still yields NULL. `COUNT(CASE WHEN d_year = y THEN 1 END) > 0` reproduces the existence requirement of the original per-year self-joins.
  - Rows with `customer_sk IS NULL` are removed, as the original join to `customer` drops them.
  - `STDDEV_SAMP` in Q74 cannot be merged from partial results, but here each (customer, year) group is computed in full.

### Q21: inventory before/after (Law I + Law III)

- **Bottleneck: a plan flip.** On SF1 the baseline drives from `date_dim` into the `inventory` primary key prefix `inv_date_sk` and only reads the date window (0.34 s). On SF2 the optimizer switches to `warehouse` → `inventory` through `inv_w`, reading **every date** for each warehouse and filtering dates afterwards through `date_dim` (25.2 s). The historical results show the same jump (0.3 s → 53.3 s).
- **Rewrite**:
  - `STRAIGHT_JOIN` fixes the plan to start from the 61-day window with a range scan on the `inventory` primary key, semi-joined with the items priced 0.99–1.49.
  - Rows are summed by `(inv_warehouse_sk, inv_item_sk)`, then joined to the dimensions and **re-aggregated by `(w_warehouse_name, i_item_id)`**.
- **Equivalence**: neither `i_item_id` (18,000 keys, 9,000 ids) nor `w_warehouse_name` (5 warehouses, 4 names) is unique, hence the second aggregation. `SUM(SUM(x))` is NULL only when every value is NULL, the same as `SUM(x)`. The ratio filter is applied after re-aggregation.

### Q47: monthly deviation with previous/next month (Law I variant + window functions)

- **Bottleneck**: aggregation by the string columns (category, brand, store name, company name, year, month), followed by a three-way self-join of the result `v1`.
- **First attempt gained only about 1.5x**: pre-aggregating by `(ss_item_sk, ss_store_sk, month)` hardly reduced the rows (1.34M → 0.96M on SF2), and the second aggregation by strings added another pass (`EXPLAIN ANALYZE`: about 4 s each). **Law I only pays off when the integer key is clearly coarser than the original grouping.**
- **Final rewrite**:
  - (category, brand) and (store name, company name) are mapped to `DENSE_RANK` integer group ids, so `store_sales` is aggregated once on integer keys, directly into 76k groups.
  - The three-way self-join is replaced with `LAG`/`LEAD`.
- **Equivalence**:
  - `DENSE_RANK`, like `GROUP BY` and `PARTITION BY`, compares strings by collation.
  - `rank()` orders by the grouping columns (year, month), so it has no ties and `rn = lag.rn + 1` is the same as `LAG(rn) = rn - 1`.
  - The original equality self-joins never match NULL, so groups with a NULL in any of the four partition columns are excluded. The rewrite drops them up front. They form whole partitions, so this does not change the average or rank of other groups.

### Q50: return intervals (Law I + Law III)

- **Bottleneck**: on SF1/SF2 the baseline is already fast (0.03–0.05 s). The historical jump (SF4 0.15 s → SF8 75.8 s) only appears at SF8 and **cannot be reproduced locally**.
- **Rewrite**:
  - `STRAIGHT_JOIN` fixes the plan as August 2001 → `store_returns` (`sr_ret_d`) → `store_sales` by primary key `(ss_item_sk, ss_ticket_number)`.
  - Counts are computed by `ss_store_sk` and re-aggregated by the ten store attributes (12 stores share 8 names).
  - `d1` is kept as a primary key lookup, preserving the check that `ss_sold_date_sk` exists in `date_dim`.
- **Purpose**: the plan no longer depends on statistics, which should prevent the SF8 plan flip. This must be confirmed on SF8.

### Q81: customers above the state average (decorrelation)

- **Bottleneck**: the baseline's average subquery is `dependent`: for every outer row it rescans the `ctr2` rows of the same state, so the work grows roughly quadratically (historical SF4 17.7 s → SF8 507.2 s). The CTE is also built by reading returns of all years through `customer_address` → `cr_a2` before the year filter.
- **Rewrite**:
  - `customer_total_return` is materialized once, driven from 2002 dates through `cr_d1`.
  - The per-state `AVG(...) * 1.2` is computed once and joined on `ctr_state`.
- **Equivalence**:
  - When `ctr_state` is NULL, the original subquery average is NULL, the comparison is NULL and the row is dropped; the join condition does not match NULL either.
  - The outer `ca_state = 'NH'` **cannot** be pushed into the CTE: it is the state of the customer's current address, while `ctr_state` is the state of the return address.

## 4. Implications for the Report

1. **Historical Q4 and Q11 timings are invalid.** The inherited versions changed the semantics: Q4 compared 2001 absolute totals instead of 2001→2002 growth, and both returned `customer_birth_country` instead of `customer_login`. On SF1 the old Q4 returns 245 rows, the original 8. The Group A draft of Q11 in the report inherits the `customer_birth_country` error.
2. **Law I is not "100% lossless" in general.** It holds only when the output attributes are functionally determined by the surrogate key and the outer query still groups by them. `i_item_id`, `w_warehouse_name` and `s_store_name` are not unique, so a second aggregation is required.
3. **Suggested highlight: Q21.** The SF1 and SF2 plans show the plan flip clearly, and the fixed plan is 133x faster on SF2. Q11 is a good example of Law I.
4. **Conclusions for SF4/SF8 need measurements**, especially for Q47, Q50 and Q81, whose main problems appear at SF8.

## 5. Measuring SF4/SF8

Prerequisites: `tpcds4` / `tpcds8` loaded, and `queries/qmod_combined/` containing the corrected Q4/Q11 (commit "fix: restore original semantics of baseline Q4 and Q11").

```bash
# Correctness (complete result sets)
python -m scripts.compare_results --sf 8 --base queries/qmod_combined --cand queries/our_opt \
  --query 4 --query 11 --query 21 --query 47 --query 50 --query 74 --query 81 --no-limit --timeout 7200
# Timing (run each three times)
python -m scripts.power_test --sf 8 --qdir queries/qmod_combined --query 4 --query 11 --query 21 \
  --query 47 --query 50 --query 74 --query 81 --warmup --timeout 7200
python -m scripts.power_test --sf 8 --qdir queries/our_opt --query 4 --query 11 --query 21 \
  --query 47 --query 50 --query 74 --query 81 --warmup --timeout 7200
```

The baseline Q4/Q11 may be very slow on SF8. A timeout is recorded as a failure in `_failures.txt` and must not be reported as a normal timing.
