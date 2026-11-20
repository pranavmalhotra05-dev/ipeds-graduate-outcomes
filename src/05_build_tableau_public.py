"""Build the Tableau Public upload set.

Reads only tableau_ready/*.csv (already suppressed at 10) and outputs/key_numbers.json
(numbers quoted in captions). Writes tableau_ready/public/: five flat CSVs, README.md and
TABLEAU_BUILD_SPEC.md. Deterministic and idempotent: run `python -I src/05_build_tableau_public.py`.
"""
import json
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "tableau_ready"
OUT = SRC / "public"
OUT.mkdir(exist_ok=True)

LEVELS = {
    "masters": ("Master's degree", 1),
    "research_doctorate": ("Doctorate: research/scholarship", 2),
    "professional_doctorate": ("Doctorate: professional practice", 3),
    "other_doctorate": ("Doctorate: other", 4),
    "all_masters_doctoral": ("All master's and doctoral levels", 0),
}
MIN_PROGRAMS_FOR_SHARE = 5  # share of completions in small programs withheld below this many such programs
BIG = 10  # display threshold


def read(name, **kw):
    return pd.read_csv(SRC / name, **kw)


def clean_text(s):
    return s.astype("string").str.replace("\u2013", "-", regex=False).str.replace("\u2014", "-", regex=False)


def yn(b):
    return b.map({True: "Yes", False: "No"})


def num_label(v, none="No data"):
    return none if pd.isna(v) else f"{int(round(v)):,}"


def pct_label(v, none="Not available"):
    return none if pd.isna(v) else f"{v * 100:.1f}%"


def write(df, name):
    df.to_csv(OUT / name, index=False, lineterminator="\n", encoding="utf-8", float_format="%.6g")


def level_cols(df):
    df["Award Level"] = df["level_key"].map(lambda k: LEVELS[k][0])
    df["Award Level Sort"] = df["level_key"].map(lambda k: LEVELS[k][1])
    return df


def year_label(y):
    return f"{y} (academic year {y - 1}-{str(y)[2:]})"


# ---------------------------------------------------------------- (1) field_year_summary
f = read("field_summary.csv", dtype={"cip2": str})
f = level_cols(f)
f["cip2_title"] = clean_text(f["cip2_title"])
susp = f["completions_suppressed"] == 1
disp = f["completions_total"].where(~susp)
assert (disp.dropna() >= BIG).all()
implied = f["share_completions_in_cells_lt10"] * f["completions_total"]
share_ok = (~susp) & (f["n_program_cells_lt10"] >= MIN_PROGRAMS_FOR_SHARE) & (implied >= BIG)
share = f["share_completions_in_cells_lt10"].where(share_ok)
field = pd.DataFrame({
    "Year": f["year"],
    "Year Label": f["year"].map(year_label),
    "CIP 2-digit Code": f["cip2"],
    "Field (CIP 2-digit family)": f["cip2"] + " " + f["cip2_title"],
    "Award Level": f["Award Level"],
    "Award Level Sort": f["Award Level Sort"],
    "Completions Displayed": disp,
    "Completions Display Label": [num_label(v, "Withheld") for v in disp],
    "Completions Suppressed": yn(susp),
    "Institutions": f["n_institutions"],
    "Programs": f["n_program_cells"],
    "Programs With Fewer Than 10 Completions": f["n_program_cells_lt10"],
    "Share of Programs With Fewer Than 10 Completions": f["share_program_cells_lt10"].round(4),
    "Programs Hidden Incl. Complementary Suppression": f["n_program_cells_suppressed_incl_complementary"],
    "Share of Completions in Programs With Fewer Than 10": share.round(4),
    "Share of Completions Display Label": [pct_label(v, "Withheld") for v in share],
    "Approximate SED Broad Field": f["sed_broad_field_approx"].fillna("Not mapped"),
})
field = field.sort_values(["Year", "Award Level Sort", "CIP 2-digit Code"], kind="mergesort").reset_index(drop=True)
write(field, "field_year_summary.csv")

# ---------------------------------------------------------------- (2) institution_summary_2023
d = read("institution_dim.csv", dtype={"unitid": str})
i = read("institution_summary.csv", dtype={"unitid": str})
i = i[i["year"] == 2023].merge(d[["unitid", "carnegie_label"]], on="unitid", how="left")
i = level_cols(i)
comp_sup = i["completions_suppressed"] == 1
comp = i["completions_total"].where(~comp_sup)
assert (comp.dropna() >= BIG).all()
is_all = i["level_key"] == "all_masters_doctoral"
enr_raw = i["grad_enrollment_total"].where(is_all)
enr_small = is_all & enr_raw.notna() & (enr_raw < BIG)
enr = enr_raw.where(~enr_small)
ratio = i["ratio_completions_to_grad_enrollment"].where(is_all & ~comp_sup & ~enr_small & enr.notna())


def enr_label(row_all, raw, small):
    if not row_all:
        return "Not reported at this level"
    if small:
        return "<10"
    return "No data" if pd.isna(raw) else f"{int(raw):,}"


def ratio_note(row_all, c_sup, small, e, r):
    if not row_all:
        return "Only reported for all levels combined"
    if c_sup:
        return "Completions withheld"
    if small:
        return "Enrollment under 10"
    if pd.isna(e):
        return "No enrollment record"
    if pd.isna(r):
        return "Not available"
    return "Ratio shown"


inst = pd.DataFrame({
    "Year": i["year"],
    "Institution ID (UNITID)": i["unitid"],
    "Institution": clean_text(i["instnm"]),
    "State": i["stabbr"],
    "Control": i["control_label"],
    "Carnegie Classification": i["carnegie_label"].fillna("Not classified"),
    "Award Level": i["Award Level"],
    "Award Level Sort": i["Award Level Sort"],
    "Completions Displayed": comp,
    "Completions Display Label": [("Withheld" if s else num_label(v)) for s, v in zip(comp_sup, comp)],
    "Completions Suppressed": yn(comp_sup),
    "Programs": i["n_program_cells"],
    "Programs Hidden Incl. Complementary Suppression": i["n_program_cells_suppressed"],
    "Graduate Enrollment Displayed": enr,
    "Graduate Enrollment Display Label": [enr_label(a, r, s) for a, r, s in zip(is_all, enr_raw, enr_small)],
    "Graduate Enrollment Under 10": yn(enr_small),
    "Completions-to-Enrollment Ratio": ratio.round(4),
    "Ratio Display Label": [("Not available" if pd.isna(r) else f"{r:.2f}") for r in ratio],
    "Ratio Status": [ratio_note(a, c, s, e, r) for a, c, s, e, r in zip(is_all, comp_sup, enr_small, enr, ratio)],
    "Ratio Above 1": yn(ratio > 1),
})
inst = inst.sort_values(["Institution ID (UNITID)", "Award Level Sort"], kind="mergesort").reset_index(drop=True)
write(inst, "institution_summary_2023.csv")

# ---------------------------------------------------------------- (3) suppression_threshold_impact
s = read("suppression_impact.csv")
s = level_cols(s)
thr_label = {5: "Under 5", 10: "Under 10 (publication default)", 20: "Under 20"}
supp = pd.DataFrame({
    "Year": s["year"],
    "Year Label": s["year"].map(year_label),
    "Threshold": s["threshold"],
    "Threshold Label": s["threshold"].map(thr_label),
    "Award Level": s["Award Level"],
    "Award Level Sort": s["Award Level Sort"],
    "Programs": s["n_cells"],
    "Programs Below Threshold": s["n_cells_primary_suppressed"],
    "Share of Programs Below Threshold": s["share_cells_primary_suppressed"].round(4),
    "Programs Hidden Incl. Complementary Suppression": s["n_cells_suppressed_total"],
    "Share of Programs Hidden Incl. Complementary": s["share_cells_suppressed_total"].round(4),
    "Total Completions (national)": s["completions_total_all_cells"],
    "Completions in Programs Below Threshold (national)": s["completions_in_primary_suppressed"],
    "Share of Completions in Programs Below Threshold": s["share_completions_in_primary_suppressed"].round(4),
    "Share of Completions in All Hidden Programs": s["share_completions_in_suppressed_total"].round(4),
    "Institutions": s["n_institutions"],
    "Institutions With Any Program Below Threshold": s["n_institutions_with_primary_suppressed"],
    "Share of Institutions With Any Program Below Threshold": s["share_institutions_with_primary_suppressed"].round(4),
    "Institutions With Every Program Below Threshold": s["n_institutions_all_cells_primary_suppressed"],
    "Share of Institutions With Every Program Below Threshold": s["share_institutions_all_cells_primary_suppressed"].round(4),
})
supp = supp.sort_values(["Year", "Threshold", "Award Level Sort"], kind="mergesort").reset_index(drop=True)
write(supp, "suppression_threshold_impact.csv")

# ---------------------------------------------------------------- (4) sed_time_to_degree
b = read("sed_benchmark.csv")
b["table_title"] = clean_text(b["table_title"])
sed = pd.DataFrame({
    "SED Table ID": b["table_id"],
    "Table Title": b["table_title"],
    "Publication Cycle": b["cycle"],
    "Newest Cycle": yn(b["is_newest_cycle"].astype(bool)),
    "Doctorate Year": b["sed_year"],
    "Field": b["field"],
    "Field Type": b["field_type"].map({"total": "All fields", "sector": "Sector", "broad_field": "Broad field"}),
    "Parent Sector": b["parent_sector"].fillna(""),
    "Time Basis": b["measure"],
    "Median Years": b["median_years"],
    "Median Years Display Label": [("Not available" if pd.isna(v) else f"{v:.1f}") for v in b["median_years"]],
    "NSF Footnote Marker": b["footnote_marker"].fillna(""),
    "Source URL": b["source_url"],
})
sed = sed.sort_values(["Publication Cycle", "Field Type", "Field", "Time Basis"], ascending=[False, True, True, True],
                      kind="mergesort").reset_index(drop=True)
write(sed, "sed_time_to_degree.csv")

# ---------------------------------------------------------------- (5) national_totals_by_level_year
n = read("national_totals.csv")
n = level_cols(n)
isall = n["level_key"] == "all_masters_doctoral"
assert (n["completions_total"] >= BIG).all()
nat = pd.DataFrame({
    "Year": n["year"],
    "Year Label": n["year"].map(year_label),
    "Award Level": n["Award Level"],
    "Award Level Sort": n["Award Level Sort"],
    "Completions": n["completions_total"],
    "Programs": n["n_program_cells"],
    "Institutions": n["n_institutions"],
    "Change vs Prior Year (%)": n["yoy_pct_change"].round(2),
    "Change vs 2020 (%)": n["pct_change_vs_2020"].round(2),
    "Graduate Enrollment (fall)": n["grad_enrollment_total"].where(isall),
    "Completions-to-Enrollment Ratio": n["ratio_completions_to_grad_enrollment_all"].where(isall).round(4),
    "Ratio Note": ["Ratio of completions to graduate enrollment; not a completion rate" if a
                   else "Not reported at this level" for a in isall],
})
nat = nat.sort_values(["Year", "Award Level Sort"], kind="mergesort").reset_index(drop=True)
write(nat, "national_totals_by_level_year.csv")

# ---------------------------------------------------------------- numbers for text (verified against key_numbers.json)
kn = json.loads((ROOT / "outputs" / "key_numbers.json").read_text(encoding="utf-8"))["numbers"]


def kv(k):
    return kn[k]["value"]


def check(val, csv_val, tol):
    assert abs(val - csv_val) <= tol, (val, csv_val)


sup23 = supp[(supp["Year"] == 2023) & (supp["Threshold"] == 10)].set_index("Award Level")
m, r = "Master's degree", "Doctorate: research/scholarship"
check(kv("supp_masters_2023_t10_share_cells_lt_threshold"), sup23.loc[m, "Share of Programs Below Threshold"], 6e-5)
check(kv("supp_research_doctorate_2023_t10_share_cells_lt_threshold"), sup23.loc[r, "Share of Programs Below Threshold"], 6e-5)
check(kv("supp_masters_2023_t10_share_completions_in_lt_threshold_cells"), sup23.loc[m, "Share of Completions in Programs Below Threshold"], 6e-5)
check(kv("supp_research_doctorate_2023_t10_share_completions_in_lt_threshold_cells"), sup23.loc[r, "Share of Completions in Programs Below Threshold"], 6e-5)
nat23 = nat[(nat["Year"] == 2023) & (nat["Award Level"] == "All master's and doctoral levels")].iloc[0]
check(kv("national_all_masters_doctoral_2023_ratio_all"), nat23["Completions-to-Enrollment Ratio"], 6e-5)
P = lambda x: f"{x * 100:.1f}%"
txt = {
    "m_prog": P(kv("supp_masters_2023_t10_share_cells_lt_threshold")),
    "r_prog": P(kv("supp_research_doctorate_2023_t10_share_cells_lt_threshold")),
    "m_comp": P(kv("supp_masters_2023_t10_share_completions_in_lt_threshold_cells")),
    "r_comp": P(kv("supp_research_doctorate_2023_t10_share_completions_in_lt_threshold_cells")),
    "ratio": f"{kv('national_all_masters_doctoral_2023_ratio_all'):.3f}",
    "m_n": f"{kv('supp_masters_2023_t10_n_cells'):,}",
    "r_n": f"{kv('supp_research_doctorate_2023_t10_n_cells'):,}",
    "all_comp": f"{int(nat23['Completions']):,}",
    "sed_new_g": f"{kv('sed_all_fields_nsf26326_2025_Since_starting_graduate_school'):.1f}",
    "sed_new_d": f"{kv('sed_all_fields_nsf26326_2025_Since_starting_doctoral_program'):.1f}",
    "sed_old_g": f"{kv('sed_all_fields_nsf25349_2024_Since_starting_graduate_school'):.1f}",
    "sed_old_d": f"{kv('sed_all_fields_nsf25349_2024_Since_starting_doctoral_program'):.1f}",
    "sed_new_b": f"{kv('sed_all_fields_nsf26326_2025_Since_earning_bachelors'):.1f}",
}
a = sed[(sed["Field"] == "All fields")].set_index(["Publication Cycle", "Time Basis"])["Median Years"]
check(kv("sed_all_fields_nsf26326_2025_Since_starting_graduate_school"), a[("nsf26326", "Since starting graduate school")], 1e-9)
check(kv("sed_all_fields_nsf25349_2024_Since_starting_doctoral_program"), a[("nsf25349", "Since starting doctoral program")], 1e-9)

# palette with computed relative luminance
PAL = [("Master's degree", "#0B1F4B", "circle"), ("Doctorate: research/scholarship", "#B5470B", "square"),
       ("Doctorate: professional practice", "#5BA3D9", "triangle"), ("Doctorate: other", "#D9D9D9", "diamond")]


def lum(hexc):
    c = [int(hexc[k:k + 2], 16) / 255 for k in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


pal_rows = "\n".join(f"| {nm} | {h} | {lum(h):.3f} | {sh} |" for nm, h, sh in PAL)
lums = [lum(h) for _, h, _ in PAL]
assert all(lums[k + 1] - lums[k] > 0.1 for k in range(3))

# ---------------------------------------------------------------- README
rows = {fn: len(pd.read_csv(OUT / fn)) for fn in
        ["field_year_summary.csv", "institution_summary_2023.csv", "suppression_threshold_impact.csv",
         "sed_time_to_degree.csv", "national_totals_by_level_year.csv"]}
readme = f"""# Tableau Public upload set

Five flat UTF-8 CSV files, each far below 10 MB, built from the suppressed tables in `tableau_ready/` by `src/05_build_tableau_public.py`. Column headers are plain names. The files need no joins or relationships; each worksheet uses one file.

## How suppression is shown

- No completions count or graduate enrollment count under 10 appears anywhere. The program-level file is not part of this set.
- A numeric "Displayed" column is empty (null) only where the matching "Suppressed" or "Under 10" column says "Yes". It is never filled with a zero. The matching "Display Label" column is always text: the number, "Withheld", "<10", "No data" or "Not available".
- Counts of programs and institutions (columns named Programs, Institutions) are counts of records, not of people, and can be small. They are published in `tableau_ready/` already.
- Shares of completions held in small programs are shown only where at least {MIN_PROGRAMS_FOR_SHARE} programs are below 10 and the implied number of completions is at least 10; otherwise the share is empty and its label says "Withheld". This prevents a single small program count being recovered from a share and a total.
- Complementary suppression (hiding the next-smallest program so a hidden count cannot be recovered by subtraction) is applied in the source and reported as "Hidden Incl. Complementary Suppression".

## Files

| File | Grain | Rows |
|---|---|---|
| field_year_summary.csv | CIP 2-digit field family x award level x year (2020-2023), national | {rows['field_year_summary.csv']:,} |
| institution_summary_2023.csv | institution x award level, 2023 only | {rows['institution_summary_2023.csv']:,} |
| suppression_threshold_impact.csv | threshold (5, 10, 20) x award level x year, national | {rows['suppression_threshold_impact.csv']:,} |
| sed_time_to_degree.csv | NSF SED cycle x field x time basis (latest year in each cycle) | {rows['sed_time_to_degree.csv']:,} |
| national_totals_by_level_year.csv | award level x year, national | {rows['national_totals_by_level_year.csv']:,} |

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
"""
(OUT / "README.md").write_text(readme, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- build spec
sed_url_new = b.loc[b["cycle"] == "nsf26326", "source_url"].iloc[0]
sed_url_old = b.loc[b["cycle"] == "nsf25349", "source_url"].iloc[0]
spec = f"""# Tableau Public build spec

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
{pal_rows}

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
- Caption (text under the sheet): "FY2023: {txt['m_prog']} of master's program records and {txt['r_prog']} of research-doctorate program records have fewer than 10 completions. Those programs hold {txt['m_comp']} of master's completions and {txt['r_comp']} of research-doctorate completions."

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
- Caption: "FY2023, one award level at a time. A field with fewer than 10 completions in total is shown as Withheld. The share of completions in small programs is withheld where fewer than {MIN_PROGRAMS_FOR_SHARE} programs are small."

### Worksheet 4: "Time to Degree Benchmark" (source: SED)

- Filters: Field = "All fields" (show as a single-value dropdown so a reader can switch to a broad field; keep Field Type in the filter list: All fields and Broad field).
- Rows: Time Basis (order: since earning bachelor's, since starting graduate school, since starting doctoral program).
- Columns: Median Years (axis from 0).
- Marks: Circle. Color and Shape: Publication Cycle (nsf26326 in #0B1F4B with circle, nsf25349 in #B5470B with square). Label: Median Years Display Label.
- Axis title: "Median years to research doctorate". Row title: "Time measured from".
- Tooltip: "Field; Publication Cycle; Doctorate Year; Time Basis; Median <Median Years Display Label> years; source table <SED Table ID>."
- Title: "Median time to a research doctorate (NSF Survey of Earned Doctorates)".
- Caption: "All fields, median years since starting graduate school / since starting the doctoral program: {txt['sed_new_g']} / {txt['sed_new_d']} for doctorate year 2025 (table nsf26326) and {txt['sed_old_g']} / {txt['sed_old_d']} for doctorate year 2024 (table nsf25349). Since earning a bachelor's degree: {txt['sed_new_b']} years (2025). Source table: Table 1-12."

## 4. Dashboard: "Graduate Program Size and Time to Degree"

1. New dashboard, Size: Fixed, 1200 x 1000.
2. Layout (vertical container, 16 px padding):
   - Row A: Title text, bold 22 pt: "Graduate Program Size and Time to Degree (IPEDS 2020-2023, NSF SED)". Under it a one-line subtitle: "Completions are degrees and awards, not students. Counts under 10 are hidden."
   - Row B (two tiles side by side, each 590 x 360): Worksheet 1 left, Worksheet 2 right, each with its caption directly beneath.
   - Row C (two tiles side by side, each 590 x 360): Worksheet 3 left, Worksheet 4 right, each with its caption directly beneath.
   - Row D: Data source note, then limits caption (text below).
3. Do not add dashboard actions that filter across worksheets: the four sheets use different sources.
4. Key figure text box (between the subtitle and Row B): "National ratio of completions to graduate enrollment, FY2023: {txt['ratio']}. This is a ratio of completions in one academic year to fall enrollment, not a completion or graduation rate. National total FY2023: {txt['all_comp']} master's and doctoral completions."
   Check it against the National source: Completions-to-Enrollment Ratio on the "All master's and doctoral levels" row for 2023 rounds to {txt['ratio']}.

### Data source note (text)

"Sources: NCES IPEDS Completions and Fall Enrollment files, file years 2020-2023 (completions final/revised release; fall 2023 enrollment provisional; 2024 completions provisional and not used), https://nces.ed.gov/ipeds/. NSF NCSES Survey of Earned Doctorates, Table 1-12, 2024 cycle ({sed_url_old}) and 2025 cycle ({sed_url_new}). Program records are first majors at the master's and doctoral levels."

### Limits caption (text)

"Counts under 10 are hidden, and the next-smallest program in a group is also hidden so hidden counts cannot be recovered. Totals of displayed programs understate true totals. The ratio is not a completion rate: enrollment includes certificate students and is not a cohort. The SED benchmark covers research doctorates only, comes from a separate survey, and has no respondent counts in the published table; the field mapping to CIP families is approximate. The sheets use FY2023 unless noted."

## 5. Accessibility

- Alt text for each sheet (Worksheet > Describe / Tooltip text on the dashboard object, Title > Alt text where available):
  1. "Bar chart. For master's, research doctorate, professional doctorate and other doctorate programs, the share of program records with fewer than 10 completions (left panel) and the share of completions held in them (right panel), FY2023. Master's {txt['m_prog']} and {txt['m_comp']}; research doctorate {txt['r_prog']} and {txt['r_comp']}."
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

- [ ] W1 FY2023 master's: share of programs below 10 = {txt['m_prog']} (suppression_threshold_impact.csv, Year 2023, Threshold 10, Master's degree), share of completions = {txt['m_comp']}.
- [ ] W1 FY2023 research doctorate: {txt['r_prog']} of programs and {txt['r_comp']} of completions.
- [ ] Program records in 2023 at threshold 10: master's {txt['m_n']}, research doctorate {txt['r_n']}.
- [ ] W2: at each level, the share hidden rises from "Under 5" to "Under 10" to "Under 20".
- [ ] W3: sum of Programs for one level in 2023 equals Programs in the Suppression source for that level.
- [ ] W3: any field showing Withheld has a null Completions Displayed and Completions Suppressed = Yes.
- [ ] W4 All fields: {txt['sed_old_g']} and {txt['sed_old_d']} for nsf25349 (2024); {txt['sed_new_g']} and {txt['sed_new_d']} for nsf26326 (2025).
- [ ] Key figure: ratio {txt['ratio']} and total {txt['all_comp']} match the National source (2023, combined row).
- [ ] Filter on the Completions Displayed field with a "minimum" check: no value below 10 in any worksheet.
- [ ] Captions contain no wording that calls the ratio a completion or graduation rate.
- [ ] Alt text, data source note and limits caption are present on the dashboard.
- [ ] Workbook opened signed out; dashboard renders with all four sheets.
"""
(OUT / "TABLEAU_BUILD_SPEC.md").write_text(spec, encoding="utf-8", newline="\n")

# ---------------------------------------------------------------- final checks
for fn in OUT.glob("*.csv"):
    assert fn.stat().st_size < 10 * 1024 * 1024, fn
for df, col in [(field, "Completions Displayed"), (inst, "Completions Displayed"),
                (inst, "Graduate Enrollment Displayed"), (nat, "Completions")]:
    v = df[col].dropna()
    assert (v >= BIG).all(), col
for df, c, flag in [(field, "Completions Displayed", "Completions Suppressed"), (inst, "Completions Displayed", "Completions Suppressed")]:
    assert (df.loc[df[c].isna(), flag] == "Yes").all() and (df.loc[df[c].notna(), flag] == "No").all()
assert (inst.loc[inst["Graduate Enrollment Displayed"].isna() & (inst["Award Level"] == "All master's and doctoral levels"),
                 "Graduate Enrollment Display Label"].isin(["<10", "No data"])).all()
for p in list(OUT.glob("*.csv")) + list(OUT.glob("*.md")):
    t = p.read_text(encoding="utf-8")
    assert "\u2013" not in t and "\u2014" not in t, p
print({k: v for k, v in rows.items()})
