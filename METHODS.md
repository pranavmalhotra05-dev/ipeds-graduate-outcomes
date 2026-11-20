# Methods

Project: IPEDS graduate outcomes (master's and doctoral completions, 2020-2023). All numbers below come from `outputs/*.md`, `outputs/key_numbers.json` or the CSVs in `tableau_ready/`; figures are produced by the scripts in `src/`. Where a number was computed for this document, the source file and formula are stated.

## 1. Sources

All IPEDS files are public zips from the NCES Data Center, pattern `https://nces.ed.gov/ipeds/datacenter/data/<FILE>.zip`. Raw zips are kept unedited in `data_raw/`; hashes and byte counts are in the `ingest_manifest` table (see `outputs/ingest_log.md`).

| source | files used | URL | years / release |
|---|---|---|---|
| IPEDS Completions (award level x CIP) | C2020_A, C2021_A, C2022_A, C2023_A, the final/revised `_RV` csv inside each zip | https://nces.ed.gov/ipeds/datacenter/data/C2020_A.zip (same pattern for 2021, 2022, 2023) | 2019-20 to 2022-23 (file year 2020-2023), final/revised |
| IPEDS Completions 2024 | C2024_A | https://nces.ed.gov/ipeds/datacenter/data/C2024_A.zip | 2023-24, PROVISIONAL (Sept 2025). Loaded to a separate table (`completions_2024_provisional`) and NOT used in any measure or output. |
| IPEDS Fall Enrollment | EF2020A, EF2021A, EF2022A (`_rv` csv), EF2023A | https://nces.ed.gov/ipeds/datacenter/data/EF2020A.zip (same pattern) | Fall 2020-2023. EF2023A has no `_RV` file and its dictionary says "Provisional release". EF2024A returned HTTP 404 (not published). |
| IPEDS Institutional Characteristics (directory) | HD2020 ... HD2024 | https://nces.ed.gov/ipeds/datacenter/data/HD2020.zip (same pattern through HD2024) | Institution name, state, control, Carnegie class. Each output year uses the HD file of the same year (institution_dim uses the latest of 2020-2023). HD2024 is loaded but not used for outputs. |
| CIP 2020 titles | CIPCode2020.csv | https://nces.ed.gov/ipeds/cipcode/Files/CIPCode2020.csv | CIP 2020 (all completions 2020-2024 use CIP 2020) |
| NSF NCSES Survey of Earned Doctorates, Table 1-12 (median years to research doctorate, by trend broad field) | nsf26326-tab001-012.xlsx and nsf25349-tab001-012.xlsx | https://ncses.nsf.gov/pubs/nsf26326/assets/data-tables/tables/nsf26326-tab001-012.xlsx and https://ncses.nsf.gov/pubs/nsf25349/assets/data-tables/tables/nsf25349-tab001-012.xlsx | nsf26326: years 1975-2025 (newest cycle); nsf25349: years 1974-2024. The two cycles share no calendar year, so they are kept side by side, not merged. |

Release handling. Each completions zip for 2020-2023 contains both an original csv and an `_rv` (final/revised) csv; only the `_rv` file is loaded. The revisions are small: for example, 2023 master's first-major completions are 947,602 in the original file and 947,728 in the revised file (`outputs/ingest_log.md`).

Published comparison figures (used only in reconciliation, section 6): NCES Digest of Education Statistics 2023, Table 318.10, https://nces.ed.gov/programs/digest/d23/tables/dt23_318.10.asp; NCSES SED 2023 page, https://ncses.nsf.gov/surveys/earned-doctorates/2023.

## 2. Analysis base

- Award levels (AWLEVEL): 7 master's; 17 doctor's research/scholarship; 18 doctor's professional practice; 19 doctor's other. `all_masters_doctoral` = 7 + 17 + 18 + 19.
- MAJORNUM = 1 only (first majors; second majors excluded). CIPCODE <> '99' (99 is a grand-total row; including it would double count).
- Program cell = institution (UNITID) x 6-digit CIP x award level x year. The base has 224,431 cells (2020-2023).
- Year = IPEDS file year. Completions year Y covers academic year Y-1 to Y (2023 = 2022-23). Enrollment year Y is fall Y, so fall 2023 is the term after the 2022-23 awards.
- Counts are degrees/awards, not students (one person with two degrees is counted twice).
- Build checks (all in `outputs/measures_log.md`): 0 duplicate cell keys, 0 HD join misses, 0 CIP title misses.

## 3. Measures (from `outputs/measure_definitions.md`)

- **completions** = ctotalt (men + women) summed over the grain.
- **grad_enrollment_total / ft / pt** = fall EFALEVEL 12 / 32 / 52 total headcount (EFTOTLT) per institution. Enrollment has no CIP or award-level detail in this file, so enrollment and any ratio exist at institution and national level only, never by CIP family or individual award level.
- **ratio_completions_to_grad_enrollment** = (master's + all doctoral completions in year Y) / (fall graduate enrollment in the same IPEDS file year Y). It is strictly a RATIO of two annual counts; it is NOT a cohort completion rate or graduation rate. The numerator students are not the denominator students; the denominator also includes post-baccalaureate and post-master's certificate students and makes no adjustment for program length (professional doctorates take 3-4 years, master's 1-2). A second variant divides by the PRIOR fall enrollment (fall Y-1, the start of the same academic year); the two variants bracket the timing problem.
- **national matched ratio** = the same ratio summed over institutions that have graduate enrollment > 0 (the all-level completions total is 0 where an institution has no master's/doctoral cells). `*_all` variants use all completions over all enrollment.
- **yoy_pct_change** = (value_Y - value_(Y-1)) / value_(Y-1) x 100; **pct_change_vs_2020** = (value_Y - value_2020) / value_2020 x 100. Every percentage is accompanied by program-cell counts (and institution counts at national/field grain) for the current, prior and 2020 values. Institution-level changes compare institution totals, so they mix new/closed programs with growth; the cell counts show this. They are empty if either side is suppressed or the base is 0/missing.
- **SED benchmark** = NSF Survey of Earned Doctorates Table 1-12, latest year of each cycle: nsf26326 (2025) and nsf25349 (2024). Three time bases exist in the table (since earning bachelor's, since starting graduate school, since starting doctoral program); there is no "registered time" row. The CIP2 to SED broad-field mapping in `field_summary.csv` (`sed_broad_field_approx`) is an approximate mapping made by the author, not an official crosswalk, and is meaningful only for research doctorates.

## 4. Suppression rules

Thresholds. Three thresholds are computed and reported (5, 10, 20) in `tableau_ready/suppression_impact.csv`. The primary threshold for every display file is **10**: a program cell with count < 10 is hidden.

Complementary suppression, as actually implemented (`sql/02_suppression_run.sql`):

1. Primary: cell count < threshold is hidden.
2. Pass 1 (family): within institution x award level x year x CIP2 family, if EXACTLY ONE cell is primary-suppressed, the next-smallest remaining (unsuppressed) cell is also hidden (ties broken by CIP code). If the family has no remaining cell, nothing more is done at this step.
3. Pass 2 (institution): within institution x award level x year, if exactly one cell is suppressed after pass 1, the next-smallest remaining cell is also hidden. This is because institution totals by level are published; otherwise the single hidden cell could be recovered by subtraction.
4. Totals: institution-level totals < 10 are hidden; the all-level institution total is also hidden if exactly one level row is hidden. Field and national totals < 10 are hidden.

Counts of extra (complementary) cells at threshold 10, 2023, from `tableau_ready/suppression_impact.csv`: all levels 2,267 (pass 1) + 149 (pass 2) = 2,416, giving 35,887 primary + 2,416 = 38,303 hidden of 57,182 cells (66.98%). Master's alone: 1,812 + 64 = 1,876. Across 2020-2023, `program_completions_by_year.csv` has 141,403 primary-suppressed, 8,779 `complementary_family` and 569 `complementary_institution` rows (total hidden 150,751 of 224,431 = 67.2%).

**Zero-count cells.** Cells reported with a count of 0 are KEPT in the base (they are reported rows in the completions file) and are treated as below every threshold: they are primary-suppressed (blank `display_count`, reason `primary_lt10`), they count toward the "share under threshold" statistics, and because the "exactly one primary-suppressed cell" tests use the same flag, a zero cell can also trigger complementary suppression of a neighbouring cell. There are 44,684 zero-count cells (19.9% of 224,431); 8,556 are 2023 master's cells. A hidden zero is indistinguishable in the display file from a hidden small positive count.

**Share of cells under 10, with and without zero-count cells** (computed from `tableau_ready/suppression_impact.csv`, threshold 10, `all_masters_doctoral` rows; excluding zeros = (n_cells_primary_suppressed - n_cells_zero_count) / (n_cells - n_cells_zero_count)):

| scope | cells | under 10 incl. zeros | zero cells | share incl. zeros | share excl. zeros |
|---|---|---|---|---|---|
| 2020 | 54,777 | 34,502 | 10,688 | 62.99% | 54.01% |
| 2021 | 55,797 | 35,369 | 11,342 | 63.39% | 54.05% |
| 2022 | 56,675 | 35,645 | 11,306 | 62.89% | 53.65% |
| 2023 | 57,182 | 35,887 | 11,348 | 62.76% | 53.54% |
| 2020-2023 pooled | 224,431 | 141,403 | 44,684 | 63.01% | 53.81% (96,719 of 179,747) |
| 2023 master's only | 42,382 | 24,935 | 8,556 | 58.83% | 48.42% (16,379 of 33,826) |

The headline "share of cells under 10" in `outputs/reconciliation.md` and `measures_log.md` (for example 58.83% of 2023 master's cells) INCLUDES zero-count cells. Share of completions that sit in cells under 10 is unaffected by zeros (they contribute 0 completions): 7.48% for 2023 master's at threshold 10.

Limitations of the rule. It is a simple two-pass rule, not an optimal secondary-suppression algorithm. After all passes no multi-cell institution x level x year group has exactly one hidden cell, but some CIP2 family groups do (threshold 10: 111 groups; thresholds 5 and 20: 172 and 67), because pass 2 can hide a cell in a different family; family totals by institution are not published in `tableau_ready`. Two hidden cells in a group still have a published combined total when the level total is shown; each hidden cell is NOT necessarily below the threshold: all 9,348 complementary-suppressed cells (2020-2023) are 10 or more (minimum 10, median about 17), and where a group has exactly two hidden cells and its total is shown, the smaller cell is bounded above by total minus 10 (bound 0 in 30 groups, at most 2 in 113, at most 4 in 205; recomputed independently from the display file). This is a simple disclosure-style rule, not a guarantee against disclosure. Privacy audit counts in `outputs/measures_log.md` are all 0: program rows with display count < 10 (0), suppressed rows with a non-blank count (0), institution or field totals < 10 (0), and files containing men/women columns (0).

Unsuppressed program cells are written only to a local file under `outputs/` that is git-ignored; it is not part of the repository and must not be published.

## 5. Privacy and FERPA note

IPEDS completions and enrollment files are aggregate, public data released by NCES. Suppression in this project follows common disclosure-avoidance practice for small cells and is applied so that dashboard and Tableau-ready files do not show small counts. It is not a claim of FERPA compliance or an institutional disclosure-review sign-off; the project holds no student-level records. Anyone merging this with institutional records should do their own disclosure review.

## 6. Reconciliation results (`outputs/reconciliation.md`, `outputs/reconciliation.json`)

- (a) Award-level totals recomputed with pandas straight from the raw zips match the DuckDB-derived numbers exactly in all 20 level-year checks (rows, institutions, completions, cells under 10).
- (b) Detail rows vs the file's own CIPCODE = 99 total rows: 0 mismatches over 3,739 / 3,778 / 3,826 / 3,833 institution-levels (2020-2023); sums equal (for example 1,155,492 in 2023).
- (c) National totals vs NCES Digest Table 318.10: IPEDS first-major counts run +1.43% to +1.59% above the Digest for master's and +1.00% to +1.29% for doctor's in 2020-2022 (within the judged +/-3% tolerance; the reason for the 1-1.6% gap was not verified). 2023 is outside tolerance (master's +7.50%, doctor's +2.72%), but the Digest 2022-23 row is labelled PROJECTED, so this is not a clean test.
- (d) NSF SED headline 57,862 new research doctorates in 2023 vs IPEDS AWLEVEL 17 first majors 82,438 (ratio 1.425; 2022: 1.398). These do not match; definitions differ (program awards classified as research/scholarship vs persons earning research doctorates) and the 40% gap was NOT investigated. Do not treat the two as comparable.

## 7. Known limits

- No graduate cohorts. IPEDS Graduation Rates (GR) covers undergraduate cohorts only, so there is no cohort completion rate, attrition or time-to-degree for master's or doctoral programs from IPEDS.
- SED is a separate, field-level source (median years to research doctorate, national). It is not linked to IPEDS institutions or programs, and its field taxonomy and year grids differ.
- The ratio is not a rate (section 3). It mixes different student populations and timing.
- Enrollment ends at fall 2023 and fall 2023 is provisional; EF2024A is not published.
- 2024 completions (C2024_A) are provisional and are not used.
- The 2023 master's jump is unexplained. National master's completions rise +5.98% in 2022-23 (894,277 to 947,728) versus +2.92% and +1.56% in the prior two years; 53,451 more master's; the ten institutions with the largest gains account for 37.1% of the change. By CIP2 family the largest master's gains are Computer and Information Sciences (+25,977), Engineering (+10,567), Multi/Interdisciplinary Studies (+6,669). The revised file differs from the original by only 126 master's, so it is not a revision effect. Whether this reflects real growth, a reporting or classification change at some institutions, or something else was not determined.
- The CIP2 to SED field mapping is approximate (section 3).
- Institution-level change percentages compare totals and so mix program openings/closings with growth (cell counts are shown beside every percentage).
- Suppression hides small cells; 62.76% of 2023 master's-and-doctoral cells are under 10 (53.54% excluding zero-count cells), though only a small share of completions sit in them (7.48% for 2023 master's), so national and field totals are reliable while program-level views are sparse.
- Institution names and Carnegie class come from HD of the same year; institutions that merge, close or change UNITID will appear as separate series.

## 8. How to rerun

```
python -I src/run_all.py
```

This runs `01_ingest.py` (download if missing, load to `data/ipeds.duckdb`), `02_build_measures.py` (SQL in `sql/`, writes `tableau_ready/` and `outputs/measures_log.md`, `measure_definitions.md`, `key_numbers.json`), `03_reconcile.py` (writes `outputs/reconciliation.md/.json`), `04_build_dashboard.py` (writes `dashboard/graduate_outcomes_dashboard.html` and a copy at `docs/index.html`), `05_build_tableau_public.py` (upload-ready CSVs and a build spec for Tableau Public in `tableau_ready/public/`) and `06_make_charts.py` (the README charts in `docs/img/`), stopping at the first failure. Dependencies are pinned in `requirements.txt`. Step 01 needs internet unless the zips are already in `data_raw/`.

## 9. Scope relative to other public IPEDS work

Many public IPEDS projects are built around undergraduate enrollment, admissions or graduation rates. This project is limited to master's and doctoral completions at program (CIP6 x award level) grain, applies and documents explicit small-cell suppression with complementary passes and threshold sensitivity (5/10/20), keeps ratios labelled as ratios rather than rates, pairs IPEDS with NSF SED time-to-degree benchmarks, and reconciles its totals against the raw files and published Digest and SED figures.
