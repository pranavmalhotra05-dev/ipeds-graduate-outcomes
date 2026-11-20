# Tableau Public upload set

Five flat UTF-8 CSV files, each far below 10 MB, built from the suppressed tables in `tableau_ready/` by `src/05_build_tableau_public.py`. Column headers are plain names. The files need no joins or relationships; each worksheet uses one file.

## How suppression is shown

- No completions count or graduate enrollment count under 10 appears anywhere. The program-level file is not part of this set.
- A numeric "Displayed" column is empty (null) only where the matching "Suppressed" or "Under 10" column says "Yes". It is never filled with a zero. The matching "Display Label" column is always text: the number, "Withheld", "<10", "No data" or "Not available".
- Counts of programs and institutions (columns named Programs, Institutions) are counts of records, not of people, and can be small. They are published in `tableau_ready/` already.
- Shares of completions held in small programs are shown only where at least 5 programs are below 10 and the implied number of completions is at least 10; otherwise the share is empty and its label says "Withheld". This prevents a single small program count being recovered from a share and a total.
- Complementary suppression (hiding the next-smallest program so a hidden count cannot be recovered by subtraction) is applied in the source and reported as "Hidden Incl. Complementary Suppression".

## Files

| File | Grain | Rows |
|---|---|---|
| field_year_summary.csv | CIP 2-digit field family x award level x year (2020-2023), national | 602 |
| institution_summary_2023.csv | institution x award level, 2023 only | 5,923 |
| suppression_threshold_impact.csv | threshold (5, 10, 20) x award level x year, national | 60 |
| sed_time_to_degree.csv | NSF SED cycle x field x time basis (latest year in each cycle) | 102 |
| national_totals_by_level_year.csv | award level x year, national | 20 |

Years: IPEDS file year. Completions cover the academic year ending in that year (2023 means 2022-23, final/revised release). Enrollment is fall of that year. Award levels: master's, research doctorate, professional-practice doctorate, other doctorate, and a combined row. Counts are degrees and awards (first majors only), not students.

## field_year_summary.csv

| Column | Meaning |
|---|---|
| Year, Year Label | IPEDS file year and a text label |
| CIP 2-digit Code, Field (CIP 2-digit family) | CIP 2020 family code and "code + title" |
| Award Level, Award Level Sort | Level name and a sort key (0 combined, 1 master's, 2 research, 3 professional, 4 other) |
| Completions Displayed | Completions in the field and level; empty if the total is under 10 |
| Completions Display Label | Text version; "Withheld" where suppressed |
| Completions Suppressed | Yes/No |
| Institutions, Programs | Institutions with at least one program; program records (institution x CIP6 x level) |
| Programs With Fewer Than 10 Completions, Share of Programs With Fewer Than 10 Completions | Programs under 10 and their share of Programs |
| Programs Hidden Incl. Complementary Suppression | Programs hidden at threshold 10 including complementary suppression |
| Share of Completions in Programs With Fewer Than 10, Share of Completions Display Label | Share of completions held in programs under 10; withheld as described above |
| Approximate SED Broad Field | Analyst mapping to an NSF SED broad field; not an official crosswalk; comparable only to research doctorates |

## institution_summary_2023.csv

Enrollment and the ratio are reported on the "All master's and doctoral levels" row only (enrollment has no level detail).

| Column | Meaning |
|---|---|
| Year | 2023 |
| Institution ID (UNITID), Institution, State, Control, Carnegie Classification | Identifiers and attributes (latest IPEDS directory year 2020-2023; Carnegie 2021 where available, else 2018) |
| Award Level, Award Level Sort | As above |
| Completions Displayed, Completions Display Label, Completions Suppressed | Completions; empty and "Withheld" where under 10 or hidden by complementary suppression |
| Programs, Programs Hidden Incl. Complementary Suppression | Program records and how many are hidden |
| Graduate Enrollment Displayed, Graduate Enrollment Display Label, Graduate Enrollment Under 10 | Fall 2023 graduate enrollment (provisional release), hidden below 10 ("<10") |
| Completions-to-Enrollment Ratio, Ratio Display Label, Ratio Status | Completions divided by graduate enrollment, only where both are displayed. A ratio, not a completion rate: enrollment includes certificate students and is not a cohort |
| Ratio Above 1 | Flags ratios above 1 for review |

## suppression_threshold_impact.csv

National aggregates for the effect of hiding programs under 5, under 10 or under 20 completions. "Share of Programs Below Threshold" is programs under the threshold divided by Programs. "Hidden Incl. Complementary" adds the extra programs hidden by complementary suppression. Completions columns are national sums.

## sed_time_to_degree.csv

NSF Survey of Earned Doctorates, Table 1-12: median years to research doctorate by broad field, for the 2024 cycle (nsf25349, doctorate year 2024) and the 2025 cycle (nsf26326, doctorate year 2025). Time Basis is one of since earning bachelor's, since starting graduate school, since starting doctoral program. Median Years is empty where NSF reports no value ("Not available"). SED covers research doctorates only and is a separate source from IPEDS; compare field by field with care.

## national_totals_by_level_year.csv

National completions, programs, institutions, percent change versus the prior year and versus 2020, and (combined row only) fall graduate enrollment and the ratio of completions to enrollment.

## Source and limits

IPEDS Completions and Fall Enrollment files (NCES), file years 2020-2023; 2024 completions are provisional and not used. NSF NCSES Survey of Earned Doctorates tables nsf25349 and nsf26326 (https://ncses.nsf.gov/). Percent columns are in percent units (4.2 means +4.2%) in the national file; shares elsewhere are fractions between 0 and 1.
