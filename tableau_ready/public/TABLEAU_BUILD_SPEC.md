# Tableau Public build spec

Status: no workbook has been built or published yet. This is a step-by-step plan for building one in Tableau Public web authoring. The author signs in and publishes; nothing here has been uploaded.

## 0. Before you start

- Files to upload (all in `tableau_ready/public/`): field_year_summary.csv, suppression_threshold_impact.csv, sed_time_to_degree.csv, national_totals_by_level_year.csv. institution_summary_2023.csv is optional (not used by the four worksheets below; upload it only if you want an institution lookup).
- Every file is its own data source. No joins and no relationships are needed. Do not blend sources; each worksheet uses exactly one.
- Dashboard size: Fixed, 1200 x 1000 px (works on a laptop; add a Phone layout if wanted).

## 1. Data connection steps

1. Open Tableau Public, create a new workbook (web authoring), choose Upload from computer.
2. Upload suppression_threshold_impact.csv. On the data source page confirm Year is a number and the shares are decimal numbers. Rename the data source "Suppression".
3. Add the other files as separate data sources (Data > New Data Source > Upload): field_year_summary.csv ("Fields"), sed_time_to_degree.csv ("SED"), national_totals_by_level_year.csv ("National").
4. In each source, set Year (and Threshold, Doctorate Year) to Dimension, discrete. Leave Award Level as a text dimension.
5. Check null handling: the numeric "Displayed" columns are empty only where the Suppressed flag is "Yes". Never replace nulls with zero.

## 2. Palette (grayscale-safe)

Four levels, ordered dark to light. Relative luminance (0 black, 1 white) differs by more than 0.1 between neighbors, so the order survives grayscale printing. Also use the shape listed, and direct labels, so color is never the only cue.

| Award Level | Hex | Relative luminance | Shape |
|---|---|---|---|
| Master's degree | #0B1F4B | 0.016 | circle |
| Doctorate: research/scholarship | #B5470B | 0.144 | square |
| Doctorate: professional practice | #5BA3D9 | 0.334 | triangle |
| Doctorate: other | #D9D9D9 | 0.694 | diamond |

Neutral text and axes: #222222. Gridlines: #E5E5E5. Use no red/green pairing. In Tableau, edit colors on the Color card (Edit Colors > Assign Palette) for each level; Tableau Public has no pattern fills, so use shapes on point charts and data labels on bars.

## 3. Worksheets

### Worksheet 1: "Small Programs by Level" (source: Suppression)

- Filters: Year = 2023; Threshold = 10; Award Level excludes "All master's and doctoral levels" (keep the four levels). Show no filter cards.
- Rows: Award Level, sorted by Award Level Sort ascending (Sort > Field > Award Level Sort, minimum).
- Columns: Share of Programs Below Threshold, then drag Share of Completions in Programs Below Threshold next to it (two panes side by side, each its own axis).
- Marks: Bar. Color: Award Level (palette above). Label: value formatted as percent, 1 decimal. Mark labels on, font 11.
- Axis titles: "Share of programs with fewer than 10 completions" and "Share of completions held in those programs". Axis fixed 0% to 100% on both panes.
- Tooltip: "Award Level; Programs: <Programs>; Programs below 10: <Programs Below Threshold>; share of programs <Share of Programs Below Threshold>; share of completions <Share of Completions in Programs Below Threshold>. Counts are program records, not people."
- Title: "Many graduate programs are small, but they hold fewer completions".
- Caption (text under the sheet): "FY2023: 58.8% of master's program records and 80.5% of research-doctorate program records have fewer than 10 completions. Those programs hold 7.5% of master's completions and 36.8% of research-doctorate completions."

### Worksheet 2: "Threshold Sensitivity" (source: Suppression)

- Filters: Year = 2023; Award Level excludes the combined row.
- Columns: Threshold Label (sorted by Threshold ascending, discrete).
- Rows: Share of Programs Hidden Incl. Complementary.
- Marks: Line with circle markers (Path off, group by Award Level). Color and Shape: Award Level (palette and shapes above). Label the last point of each line with the Award Level name (Label > Marks to label: Most recent / Line ends).
- Axis titles: "Hiding rule (completions below)" and "Share of programs hidden, including complementary suppression". Axis 0% to 100%.
- Tooltip: "Award Level; Threshold Label; Programs hidden <Programs Hidden Incl. Complementary Suppression> of <Programs>; share hidden <Share of Programs Hidden Incl. Complementary>."
- Title: "Raising the hiding rule hides more programs".
- Caption: "FY2023 national program records. Thresholds of 5, 10 and 20 completions are shown; 10 is the publication default. Complementary suppression also hides the next-smallest program in a group so a hidden count cannot be recovered by subtraction."

### Worksheet 3: "Field Detail" (source: Fields)

- Filters: Year = 2023 (single value); Award Level = "Master's degree" (show this filter as a single-value dropdown on the sheet; allow the four levels, exclude the combined row); Share of Programs With Fewer Than 10 Completions: keep All.
- Rows: Field (CIP 2-digit family), sorted descending by Share of Programs With Fewer Than 10 Completions.
- Columns: Share of Programs With Fewer Than 10 Completions.
- Marks: Bar. Color: a single color (#0B1F4B) for all bars, because the level is chosen by the filter. Label: Programs With Fewer Than 10 Completions out of Programs, shown in the tooltip, and the percent as the bar label.
- Axis title: "Share of programs with fewer than 10 completions". Axis 0% to 100%.
- Tooltip: "Field; Award Level; Completions: <Completions Display Label>; Programs: <Programs>; programs below 10: <Programs With Fewer Than 10 Completions>; share of completions in those programs: <Share of Completions Display Label>."
- Title: "Small programs by field".
- Caption: "FY2023, one award level at a time. A field with fewer than 10 completions in total is shown as Withheld. The share of completions in small programs is withheld where fewer than 5 programs are small."

### Worksheet 4: "Time to Degree Benchmark" (source: SED)

- Filters: Field = "All fields" (show as a single-value dropdown so a reader can switch to a broad field; keep Field Type in the filter list: All fields and Broad field).
- Rows: Time Basis (order: since earning bachelor's, since starting graduate school, since starting doctoral program).
- Columns: Median Years (axis from 0).
- Marks: Circle. Color and Shape: Publication Cycle (nsf26326 in #0B1F4B with circle, nsf25349 in #B5470B with square). Label: Median Years Display Label.
- Axis title: "Median years to research doctorate". Row title: "Time measured from".
- Tooltip: "Field; Publication Cycle; Doctorate Year; Time Basis; Median <Median Years Display Label> years; source table <SED Table ID>."
- Title: "Median time to a research doctorate (NSF Survey of Earned Doctorates)".
- Caption: "All fields, median years since starting graduate school / since starting the doctoral program: 7.0 / 5.8 for doctorate year 2025 (table nsf26326) and 7.3 / 5.7 for doctorate year 2024 (table nsf25349). Since earning a bachelor's degree: 8.6 years (2025). Source table: Table 1-12."

## 4. Dashboard: "Graduate Program Size and Time to Degree"

1. New dashboard, Size: Fixed, 1200 x 1000.
2. Layout (vertical container, 16 px padding):
   - Row A: Title text, bold 22 pt: "Graduate Program Size and Time to Degree (IPEDS 2020-2023, NSF SED)". Under it a one-line subtitle: "Completions are degrees and awards, not students. Counts under 10 are hidden."
   - Row B (two tiles side by side, each 590 x 360): Worksheet 1 left, Worksheet 2 right, each with its caption directly beneath.
   - Row C (two tiles side by side, each 590 x 360): Worksheet 3 left, Worksheet 4 right, each with its caption directly beneath.
   - Row D: Data source note, then limits caption (text below).
3. Do not add dashboard actions that filter across worksheets: the four sheets use different sources.
4. Key figure text box (between the subtitle and Row B): "National ratio of completions to graduate enrollment, FY2023: 0.353. This is a ratio of completions in one academic year to fall enrollment, not a completion or graduation rate. National total FY2023: 1,155,492 master's and doctoral completions."
   Check it against the National source: Completions-to-Enrollment Ratio on the "All master's and doctoral levels" row for 2023 rounds to 0.353.

### Data source note (text)

"Sources: NCES IPEDS Completions and Fall Enrollment files, file years 2020-2023 (completions final/revised release; fall 2023 enrollment provisional; 2024 completions provisional and not used), https://nces.ed.gov/ipeds/. NSF NCSES Survey of Earned Doctorates, Table 1-12, 2024 cycle (https://ncses.nsf.gov/pubs/nsf25349/assets/data-tables/tables/nsf25349-tab001-012.xlsx) and 2025 cycle (https://ncses.nsf.gov/pubs/nsf26326/assets/data-tables/tables/nsf26326-tab001-012.xlsx). Program records are first majors at the master's and doctoral levels."

### Limits caption (text)

"Counts under 10 are hidden, and the next-smallest program in a group is also hidden so hidden counts cannot be recovered. Totals of displayed programs understate true totals. The ratio is not a completion rate: enrollment includes certificate students and is not a cohort. The SED benchmark covers research doctorates only, comes from a separate survey, and has no respondent counts in the published table; the field mapping to CIP families is approximate. The sheets use FY2023 unless noted."

## 5. Accessibility

- Alt text for each sheet (Worksheet > Describe / Tooltip text on the dashboard object, Title > Alt text where available):
  1. "Bar chart. For master's, research doctorate, professional doctorate and other doctorate programs, the share of program records with fewer than 10 completions (left panel) and the share of completions held in them (right panel), FY2023. Master's 58.8% and 7.5%; research doctorate 80.5% and 36.8%."
  2. "Line chart. Share of program records hidden when the hiding rule is under 5, under 10 or under 20 completions, by award level, FY2023. Higher thresholds hide a larger share at every level."
  3. "Bar chart. For the selected award level, the share of programs with fewer than 10 completions in each field family, FY2023, sorted from highest to lowest."
  4. "Dot chart. Median years to a research doctorate for all fields, from three starting points, for doctorate years 2024 and 2025."
- Do not rely on color alone: point shapes, direct labels, and the data tables behind the CSVs.
- Minimum font 11 pt for labels; contrast of text on white at least 4.5:1 (#222222).

## 6. Publish settings (the author does this)

1. Save to Tableau Public: Public visibility. Title: "Graduate Program Size and Time to Degree".
2. Decide whether to allow download of the workbook and data (Settings > Allow downloads). The data are suppressed and public sources, so either choice is acceptable; this is the author's choice.
3. Add a description with the data sources and the limits caption, and link the repository README.
4. Confirm the dashboard opens in a signed-out browser window.
5. Reminder: no workbook has been published yet.

## 7. Verification checklist (compare the dashboard with the CSVs)

- [ ] W1 FY2023 master's: share of programs below 10 = 58.8% (suppression_threshold_impact.csv, Year 2023, Threshold 10, Master's degree), share of completions = 7.5%.
- [ ] W1 FY2023 research doctorate: 80.5% of programs and 36.8% of completions.
- [ ] Program records in 2023 at threshold 10: master's 42,382, research doctorate 12,326.
- [ ] W2: at each level, the share hidden rises from "Under 5" to "Under 10" to "Under 20".
- [ ] W3: sum of Programs for one level in 2023 equals Programs in the Suppression source for that level.
- [ ] W3: any field showing Withheld has a null Completions Displayed and Completions Suppressed = Yes.
- [ ] W4 All fields: 7.3 and 5.7 for nsf25349 (2024); 7.0 and 5.8 for nsf26326 (2025).
- [ ] Key figure: ratio 0.353 and total 1,155,492 match the National source (2023, combined row).
- [ ] Filter on the Completions Displayed field with a "minimum" check: no value below 10 in any worksheet.
- [ ] Captions contain no wording that calls the ratio a completion or graduation rate.
- [ ] Alt text, data source note and limits caption are present on the dashboard.
- [ ] Workbook opened signed out; dashboard renders with all four sheets.
