# Summary briefs
Four one-page briefs, one per dashboard view. Data: IPEDS completions 2020-2023 (final/revised), first majors, master's and doctoral; see METHODS.md. Descriptive only; no causal claims.
Source tags: [KN] outputs/key_numbers.json; [TR:file] a tableau_ready CSV as is; [CALC] computed read-only from tableau_ready (snippet in appendix).
Illustrative institution: University of Michigan-Ann Arbor (UNITID 170976, public), used only to show how an institution-level brief reads when built from public data. It was chosen because it is a large public university with complete institution totals in all four years. The figures are read from public IPEDS files and are not a finding about that institution.
Cautions: the 2023 national master's rise is unexplained (METHODS s.7). Counts are awards, not students. Fall 2023 enrollment is provisional.

## 1. Program director (example: Information Science/Studies CIP 11.0401, master's)
- What changed: 198 awards in 2022, 279 in 2023, +81 or +40.9% [CALC 279/198-1]; vs 2020 (218) +28.0%. n = 1 program cell at 1 institution each year; displayed all four years (218, 242, 198, 279).
- Context: nationally CIP 11 master's rose +50.2% (77,725 vs 51,748 awards; 1,438 vs 1,372 cells; 676 vs 666 institutions) [TR:field_summary]. All master's: +5.98% (947,728 vs 894,277; 42,382 vs 41,904 cells; 2,021 vs 2,020 institutions) [KN national_masters_2023_*].
- What to do: check against registrar records whether 2023 reflects a larger cohort, coding change or one-year swing (2022 was the low). Use the 2020-2023 series.
- Limits: one cell; small counts swing; awards, not a rate; cells under 10 hidden.

## 2. Dean (example: Business CIP 52 and Engineering CIP 14, master's)
Only cells displayed in BOTH years are compared.
- Business: 6 cells; 3 matched, 803 to 969 awards, +20.7% [CALC]; 2 cells hidden each year (different cells). 52.0201: 603 to 706 (+17.1%).
- Engineering: 25 cells; 17 matched, 1,051 to 1,473, +40.2% [CALC]; 8 cells hidden in one or both years.
- Context: national master's Engineering +24.2% (54,261 vs 43,694; 2,325 vs 2,295 cells; 385 vs 379 institutions); Business +1.30% (211,299 vs 208,593; 4,732 vs 4,661; 1,327 vs 1,322) [TR:field_summary].
- What to do: compare with your own records; matched cells are a floor. Ask departments whether increases are new cohorts or timing.
- Limits: hidden cells unrecoverable; no field-level enrollment in IPEDS here, so no ratio.

## 3. Graduate dean (example institution, all master's and doctoral)
- What changed: 6,361 to 7,605, +19.6% (277 and 276 cells); +20.4% vs 2020 (6,316; 257 cells) [TR:institution_summary]. Master's 4,731 to 5,965 (+26.1%; 157, 156 cells); research doctorate 892 to 925 (+3.7%; 111, 111); professional doctorate 738 to 715 (-3.1%; 9, 9).
- Ratio (not a rate): 0.415 in 2023 (7,605/18,335) vs 0.343 in 2022; national matched 0.353 (1,155,191/3,274,596; 2,048 institutions) [KN national_all_masters_doctoral_2023_ratio_matched].
- What to do: reconcile the 2023 master's rise with institutional records before planning; track the series; use own cohort records for completion/time-to-degree (IPEDS has no graduate cohorts).
- Benchmark (separate source): NSF SED Table 1-12 all fields, median years since starting doctoral program 5.7 (2024, nsf25349) and 5.8 (2025, nsf26326); since starting grad school 7.3 and 7.0. National, not matched to this institution.
- Limits: 173 of 276 cells hidden in 2023; enrollment provisional.

## 4. Provost (example institution vs national)
- What changed: 7,605 in 2023, +19.6% vs 2022 and +20.4% vs 2020 (276 cells vs 277 and 257). National: 1,155,492, +4.97% vs 2022 (1,100,797) and +10.30% vs 2020 (1,047,606); 57,182 cells, 2,057 institutions (56,675 cells, 2,059 in 2022) [KN].
- Context [CALC, institution_summary 2023 all_masters_doctoral]: of 2,090 rows, 1,315 have a computable change; median +0.60% (quartiles -9.73% to +13.16%); 224 other institutions grew more than +19.56% (225 counting the example). Public: 420 of 578 rows computable, median +3.47%. The example ranks 14th of 1,455 rows with a displayed total. Percentages mix new/closed programs with growth.
- What to do: treat the jump as a prompt to validate reporting, program counts and timing, not as a performance result; do not set targets from the ratio or one year.
- Limits: no causal claims; 2024 completions provisional and excluded; medians are unweighted.

## Appendix (read-only pandas on tableau_ready)
Filter program_completions_by_year to unitid 170976, level masters; pivot display_count by cipcode and year for CIP2 52 and 14, keep cells non-null in 2022 and 2023, sum. Institution rows: institution_summary where level_key == all_masters_doctoral and year == 2023; take yoy_pct_change median and quantiles, and count completions_total > 7605 plus 1.
