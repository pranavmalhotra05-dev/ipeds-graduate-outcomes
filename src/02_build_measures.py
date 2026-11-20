"""02_build_measures.py - analysis base, measures, small-cell suppression, dashboard-ready CSVs.

Idempotent: every m_* table in data/ipeds.duckdb is rebuilt on each run (ingest tables are never altered).
SQL lives in sql/*.sql and is executed here in order.

Run:  python -I src/02_build_measures.py      (then: python -I src/03_reconcile.py)
"""
import datetime as dt
import io
import json
import re
import zipfile
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
SQL = ROOT / "sql"
OUT = ROOT / "outputs"
TAB = ROOT / "tableau_ready"
DB = ROOT / "data" / "ipeds.duckdb"
SCRIPT = "src/02_build_measures.py"
THRESHOLDS = [5, 10, 20]
LEVELS = ["masters", "research_doctorate", "professional_doctorate", "other_doctorate", "all_masters_doctoral"]
YEARS = [2020, 2021, 2022, 2023]
for p in (OUT, TAB):
    p.mkdir(exist_ok=True)

con = duckdb.connect(str(DB))
con.execute("PRAGMA threads=4")


def run_sql(name, repl=None):
    text = (SQL / name).read_text(encoding="utf-8")
    if repl:
        for k, v in repl.items():
            text = text.replace(k, str(v))
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))
    for stmt in text.split(";"):
        if stmt.strip():
            con.execute(stmt)


def q(sql):
    return con.execute(sql).df()


def scalar(sql):
    return con.execute(sql).fetchone()[0]


# ---------------------------------------------------------------- dimension tables built in Python
SMALL = {"and", "of", "the", "in", "for", "or", "to", "a", "an", "on", "with"}


def title_case(s):
    def f(m):
        w = m.group(0).lower()
        return w if w in SMALL and m.start() > 0 else w.capitalize()
    return re.sub(r"[A-Za-z]+", f, s)


fam = q("select family2 as cip2, title from cip_titles where cip_level = 'family'")
fam["cip2_title"] = fam["title"].map(title_case)
cip2_dim = fam[["cip2", "cip2_title"]]
con.register("cip2_dim_df", cip2_dim)
con.execute("create or replace table m_cip2_dim as select * from cip2_dim_df")

zf = zipfile.ZipFile(RAW / "HD2023_Dict.zip")
wb = openpyxl.load_workbook(io.BytesIO(zf.read("HD2023_dict.xlsx")), read_only=True)
rows = []
for r in wb["Frequencies"].iter_rows(values_only=True):
    if r[1] in ("C21BASIC", "C18BASIC") and r[2] is not None:
        rows.append({"vintage": "2021" if r[1] == "C21BASIC" else "2018", "code": int(r[2]),
                     "label": str(r[3]).strip()})
car = pd.DataFrame(rows)
con.register("carnegie_df", car)
con.execute("create or replace table m_carnegie_dim as select * from carnegie_df")

# ---------------------------------------------------------------- run SQL
run_sql("01_base.sql")
run_sql("02_suppression_init.sql")
for thr in THRESHOLDS:
    run_sql("02_suppression_run.sql", {"${thr}": thr})
run_sql("03_measures.sql")
run_sql("04_suppression_impact.sql")
run_sql("05_display.sql")

# ---------------------------------------------------------------- integrity checks (fail loudly)
checks = {}
n_cells = scalar("select count(*) from m_program_cells")
n_expected = scalar("select count(*) from completions where majornum = 1 and cipcode <> '99' and awlevel in (7,17,18,19)")
assert n_cells == n_expected, (n_cells, n_expected)
checks["program_cells_rows"] = n_cells
dup = scalar("select count(*) from (select unitid, year, cipcode, awlevel from m_program_cells group by all having count(*) > 1)")
assert dup == 0
checks["duplicate_program_cell_keys"] = dup
checks["hd_join_misses"] = scalar("select count(*) from m_program_cells where hd_join_miss")
checks["cip_program_title_misses"] = scalar("select count(*) from m_program_cells where cip_title is null")
checks["cip2_family_title_misses"] = scalar("select count(*) from m_program_cells where cip2_title is null")
checks["carnegie_label_misses_where_code_present"] = scalar(
    "select count(*) from m_program_cells where carnegie_basic is not null and carnegie_label is null")
checks["zero_count_cells"] = scalar("select count(*) from m_program_cells where completions = 0")
checks["zero_count_cells_2023_masters"] = scalar(
    "select count(*) from m_program_cells where completions = 0 and year = 2023 and awlevel = 7")
checks["ft_plus_pt_ne_total_rows"] = scalar(
    "select count(*) from m_inst_enrollment where grad_enrollment_total <> grad_enrollment_ft + grad_enrollment_pt")
checks["supp_rows_expected"] = n_cells * len(THRESHOLDS)
assert scalar("select count(*) from m_cell_supp") == n_cells * len(THRESHOLDS)
checks["completions_cells_with_no_enrollment_row_2023"] = scalar(
    "select count(*) from m_program_cells c where year = 2023 and not exists "
    "(select 1 from m_inst_enrollment e where e.unitid = c.unitid and e.year = c.year)")
checks["institutions_with_completions_but_no_graduate_enrollment_2023"] = scalar(
    "select count(distinct unitid) from m_program_cells c where year = 2023 and not exists "
    "(select 1 from m_inst_enrollment e where e.unitid = c.unitid and e.year = c.year)")
checks["enrollment_only_institutions_2023"] = scalar(
    "select count(*) from m_inst_enrollment e where year = 2023 and not exists "
    "(select 1 from m_program_cells c where c.unitid = e.unitid and c.year = e.year)")

# residual disclosure check: after complementary suppression no institution x level x year group has exactly one suppressed cell
# except groups of a single program cell (then the cell is the whole institution-level total, which is itself suppressed as <10)
resid = q("""
select thr, count(*) as n_groups from (
  select s.thr, s.unitid, s.year, s.awlevel, sum(s.suppressed::int) ns, count(*) n
  from m_cell_supp s group by all) g
where ns = 1 and n > 1 group by thr order by thr""")
checks["residual_inst_level_groups_with_exactly_one_suppressed_cell_multi_cell_groups"] = {int(r.thr): int(r.n_groups) for r in resid.itertuples()}
resid_fam = q("""
select thr, count(*) as n_groups from (
  select s.thr, s.unitid, s.year, s.awlevel, left(s.cipcode,2) cip2, sum(s.suppressed::int) ns, count(*) n
  from m_cell_supp s group by all) g
where ns = 1 and n > 1 group by thr order by thr""")
checks["family_groups_with_exactly_one_suppressed_cell_after_all_passes_multi_cell_groups"] = {int(r.thr): int(r.n_groups) for r in resid_fam.itertuples()}

# ---------------------------------------------------------------- exports
# column dictionary (every exported column must be described here)
D = {
    "year": "IPEDS file year. Completions: academic year ending that year (2023 = 2022-23, final/revised _RV file). Enrollment: fall of that year.",
    "unitid": "IPEDS institution identifier (UNITID).",
    "instnm": "Institution name from the HD file of the same year (institution_dim: latest HD year 2020-2023).",
    "stabbr": "Two-letter state/territory abbreviation (HD).",
    "control_label": "Control of institution from HD CONTROL: Public, Private not-for-profit, Private for-profit, Not available.",
    "cipcode": "6-digit CIP 2020 program code (dd.dddd).",
    "cip_title": "CIP 2020 program title.",
    "cip2": "2-digit CIP family code (first two characters of cipcode).",
    "cip2_title": "CIP 2020 family title (title-cased).",
    "award_level_code": "IPEDS AWLEVEL code: 7 master's, 17 doctor's research/scholarship, 18 doctor's professional practice, 19 doctor's other.",
    "level_key": "Award level key: masters, research_doctorate, professional_doctorate, other_doctorate, or all_masters_doctoral (sum of 7+17+18+19).",
    "award_level": "Award level label.",
    "suppressed": "1 if the count is withheld (primary: count below 10; or complementary suppression), else 0.",
    "suppression_reason": "none, primary_lt10, complementary_family (next-smallest cell in institution x level x year x CIP2 family group), complementary_institution (next-smallest cell in institution x level x year group).",
    "display_count": "Completions (first majors only) in the program cell; EMPTY when suppressed = 1.",
    "suppression_threshold": "Primary suppression threshold applied (10).",
    "completions_total": "Sum of completions in the grain; EMPTY when the total is itself below 10 (or, institution all-level row, when exactly one level row is hidden).",
    "completions_suppressed": "1 if completions_total is withheld, else 0.",
    "n_program_cells": "Number of program cells (institution x CIP6 x level) behind the total in the same row.",
    "n_program_cells_suppressed": "Number of those program cells that are suppressed in program_completions_by_year (threshold 10 incl. complementary).",
    "grad_enrollment_total": "Fall graduate enrollment, EFALEVEL 12 (all graduate students, full + part time). Provided on the all_masters_doctoral row only. Includes graduate students in post-baccalaureate/post-master's certificate programs (not in the completions numerator).",
    "grad_enrollment_ft": "Fall graduate enrollment, full-time (EFALEVEL 32). all_masters_doctoral row only.",
    "grad_enrollment_pt": "Fall graduate enrollment, part-time (EFALEVEL 52). all_masters_doctoral row only.",
    "ratio_completions_to_grad_enrollment": "RATIO, NOT a cohort completion rate: master's+doctoral completions (AY ending in year) / fall graduate enrollment of the same IPEDS file year. Empty when completions_total suppressed or enrollment missing/0.",
    "ratio_completions_to_prior_fall_grad_enrollment": "Same numerator over the PRIOR fall's graduate enrollment (fall at the start of the same academic year). Years 2021-2023 only.",
    "completions_prior_year": "Completions_total of the prior IPEDS year in the same grain; EMPTY if that value is suppressed/unavailable.",
    "n_program_cells_prior_year": "Program cells behind completions_prior_year.",
    "yoy_pct_change": "Percent change vs the prior year (4.2 = +4.2%). Empty if either side suppressed or prior is 0/missing.",
    "completions_2020": "Completions_total in 2020 (base year) in the same grain; EMPTY if suppressed/unavailable.",
    "n_program_cells_2020": "Program cells behind completions_2020.",
    "pct_change_vs_2020": "Percent change vs 2020 (2021-2023 rows). Empty if either side suppressed or 2020 is 0/missing.",
    "n_institutions": "Number of distinct institutions with at least one program cell in the grain.",
    "n_institutions_prior_year": "Institutions behind the prior-year value.",
    "n_institutions_2020": "Institutions behind the 2020 value.",
    "n_institutions_with_enrollment": "Institutions with a graduate enrollment record (EFALEVEL 12) in that year (national_totals, all_masters_doctoral row).",
    "matched_completions": "Master's+doctoral completions at institutions that have graduate enrollment > 0 (used for the matched ratio).",
    "matched_enrollment": "Graduate enrollment at those same institutions.",
    "n_matched_institutions": "Institutions behind the matched ratio.",
    "ratio_completions_to_grad_enrollment_matched": "RATIO, NOT a cohort completion rate: matched_completions / matched_enrollment (same IPEDS file year).",
    "ratio_completions_to_grad_enrollment_all": "RATIO: all completions / all graduate enrollment (includes completions at institutions with no graduate enrollment record).",
    "ratio_completions_to_prior_fall_grad_enrollment_matched": "RATIO: completions in year / prior fall graduate enrollment, institutions with both. 2021-2023, all_masters_doctoral row only.",
    "n_matched_institutions_prior_fall": "Institutions behind the prior-fall ratio.",
    "n_program_cells_lt10": "Program cells with a count below 10 (primary suppression only).",
    "share_program_cells_lt10": "n_program_cells_lt10 / n_program_cells.",
    "share_completions_in_cells_lt10": "Share of completions that sit in cells with count below 10.",
    "n_program_cells_suppressed_incl_complementary": "Program cells suppressed at threshold 10 including complementary suppression.",
    "sed_broad_field_approx": "APPROXIMATE mapping, made by the author, of the CIP2 family to an NSF SED trend broad field (not an official crosswalk; empty where unmapped). Comparable only to research doctorates.",
    "threshold": "Primary suppression threshold (count below this value is suppressed): 5, 10 or 20.",
    "n_cells": "Number of program cells.",
    "n_cells_primary_suppressed": "Cells with count below the threshold (zero counts included).",
    "share_cells_primary_suppressed": "n_cells_primary_suppressed / n_cells.",
    "n_cells_complementary_family": "Extra cells hidden by pass 1: within an institution x level x year x CIP2 family group, if exactly one cell was primary-suppressed the next-smallest cell is also hidden.",
    "n_cells_complementary_institution": "Extra cells hidden by pass 2: within an institution x level x year group, if exactly one cell is hidden after pass 1 the next-smallest cell is also hidden.",
    "n_cells_suppressed_total": "Primary + complementary suppressed cells.",
    "share_cells_suppressed_total": "n_cells_suppressed_total / n_cells.",
    "completions_total_all_cells": "Sum of completions in all cells (published only as a national aggregate in this file).",
    "completions_in_primary_suppressed": "Completions that sit in primary-suppressed cells (national aggregate).",
    "share_completions_in_primary_suppressed": "Share of all completions in primary-suppressed cells.",
    "completions_in_suppressed_total": "Completions in primary + complementary suppressed cells (national aggregate).",
    "share_completions_in_suppressed_total": "Share of all completions in all suppressed cells.",
    "n_cells_zero_count": "Cells that are reported with a count of 0 (included in the base and counted as below threshold).",
    "n_institutions_with_primary_suppressed": "Institutions with at least one primary-suppressed cell.",
    "share_institutions_with_primary_suppressed": "Share of institutions with at least one primary-suppressed cell.",
    "n_institutions_with_any_suppressed": "Institutions with at least one suppressed cell (primary or complementary).",
    "n_institutions_all_cells_primary_suppressed": "Institutions where EVERY program cell is below the threshold.",
    "share_institutions_all_cells_primary_suppressed": "Share of institutions where every program cell is below the threshold.",
    "n_institutions_all_cells_suppressed_total": "Institutions where every program cell is suppressed (primary or complementary).",
    "share_institutions_all_cells_suppressed_total": "Share of institutions where every cell is suppressed (primary or complementary).",
    "table_id": "NSF SED table identifier (Table 1-12: median years to research doctorate, by trend broad field).",
    "cycle": "NSF publication cycle: nsf26326 (newest, data years through 2025) or nsf25349 (2024 cycle).",
    "is_newest_cycle": "True for nsf26326.",
    "sed_year": "SED doctorate year of the value (latest year in the cycle: 2025 for nsf26326, 2024 for nsf25349).",
    "field": "NSF SED field label (All fields, sector, or trend broad field).",
    "field_type": "total, sector or broad_field.",
    "parent_sector": "Science and engineering / Non-science and engineering for broad fields.",
    "measure": "Time basis: Since earning bachelor's, Since starting graduate school, Since starting doctoral program.",
    "median_years": "Median years (numeric); empty if not available.",
    "value_raw": "Value as in the NSF workbook (e.g. 'na').",
    "footnote_marker": "NSF footnote marker, if any.",
    "table_title": "NSF table title.",
    "source_url": "Source xlsx URL.",
    "control": "HD CONTROL code (1 public, 2 private not-for-profit, 3 private for-profit, -3 not available).",
    "sector": "HD SECTOR code.",
    "carnegie_basic": "Carnegie basic classification code (2021 vintage when populated, else 2018).",
    "carnegie_basic_vintage": "Vintage of carnegie_basic: 2021 or 2018.",
    "carnegie_label": "Carnegie basic classification label (from HD2023 dictionary).",
    "hd_year_used": "HD year the attributes were taken from (latest in 2020-2023).",
    "first_completions_year": "First year (2020-2023) with a master's/doctoral program cell.",
    "last_completions_year": "Last year (2020-2023) with a master's/doctoral program cell.",
    "n_years_with_completions": "Years (of 4) with at least one master's/doctoral program cell.",
    "has_graduate_enrollment": "True if the institution has a graduate enrollment record in any year 2020-2023.",
}

EXPORTS = [
    ("program_completions_by_year",
     "select year, unitid, instnm, stabbr, control_label, cipcode, cip_title, cip2, cip2_title, award_level_code, level_key, "
     "award_level, suppressed, suppression_reason, display_count, suppression_threshold "
     "from m_program_display order by year, unitid, award_level_code, cipcode",
     "one row per institution x CIP6 program x award level x year (2020-2023, final/revised data)"),
    ("institution_summary",
     "select year, unitid, instnm, stabbr, control_label, level_key, award_level, completions_total, completions_suppressed, "
     "n_program_cells, n_program_cells_suppressed, grad_enrollment_total, grad_enrollment_ft, grad_enrollment_pt, "
     "ratio_completions_to_grad_enrollment, ratio_completions_to_prior_fall_grad_enrollment, completions_prior_year, "
     "n_program_cells_prior_year, yoy_pct_change, completions_2020, n_program_cells_2020, pct_change_vs_2020 "
     "from m_inst_summary_display order by year, unitid, level_key",
     "one row per institution x year x award level (4 levels + all_masters_doctoral)"),
    ("field_summary",
     "select year, cip2, cip2_title, level_key, award_level, completions_total, completions_suppressed, n_institutions, "
     "n_program_cells, n_program_cells_lt10, share_program_cells_lt10, share_completions_in_cells_lt10, "
     "n_program_cells_suppressed_incl_complementary, completions_prior_year, n_program_cells_prior_year, n_institutions_prior_year, "
     "yoy_pct_change, completions_2020, n_program_cells_2020, n_institutions_2020, pct_change_vs_2020, sed_broad_field_approx "
     "from m_field_display order by year, cip2, level_key",
     "one row per CIP2 family x award level (4 levels + all_masters_doctoral) x year, national"),
    ("suppression_impact",
     "select threshold, year, level_key, n_cells, n_cells_primary_suppressed, share_cells_primary_suppressed, "
     "n_cells_complementary_family, n_cells_complementary_institution, n_cells_suppressed_total, share_cells_suppressed_total, "
     "completions_total as completions_total_all_cells, completions_in_primary_suppressed, share_completions_in_primary_suppressed, "
     "completions_in_suppressed_total, share_completions_in_suppressed_total, n_cells_zero_count, n_institutions, "
     "n_institutions_with_primary_suppressed, share_institutions_with_primary_suppressed, n_institutions_with_any_suppressed, "
     "n_institutions_all_cells_primary_suppressed, share_institutions_all_cells_primary_suppressed, "
     "n_institutions_all_cells_suppressed_total, share_institutions_all_cells_suppressed_total "
     "from m_supp_impact order by threshold, year, level_key",
     "one row per threshold (5/10/20) x award level (4 + all_masters_doctoral) x year"),
    ("sed_benchmark",
     "select table_id, cycle, is_newest_cycle, sed_year, field, field_type, parent_sector, measure, median_years, value_raw, "
     "footnote_marker, table_title, source_url from m_sed_benchmark order by is_newest_cycle desc, measure, field_type, field",
     "one row per SED cycle x field x time-basis measure (latest year in each cycle only)"),
    ("national_totals",
     "select year, level_key, award_level, completions_total, n_program_cells, n_institutions, grad_enrollment_total, grad_enrollment_ft, "
     "grad_enrollment_pt, n_institutions_with_enrollment, matched_completions, matched_enrollment, n_matched_institutions, "
     "ratio_completions_to_grad_enrollment_matched, ratio_completions_to_grad_enrollment_all, "
     "ratio_completions_to_prior_fall_grad_enrollment_matched, n_matched_institutions_prior_fall, completions_prior_year, "
     "n_program_cells_prior_year, n_institutions_prior_year, yoy_pct_change, completions_2020, n_program_cells_2020, "
     "n_institutions_2020, pct_change_vs_2020 from m_national_display order by year, level_key",
     "one row per award level (4 + all_masters_doctoral) x year, national"),
    ("institution_dim",
     "select unitid, instnm, stabbr, control, control_label, sector, carnegie_basic, carnegie_basic_vintage, carnegie_label, "
     "hd_year_used, first_completions_year, last_completions_year, n_years_with_completions, has_graduate_enrollment "
     "from m_institution_dim order by unitid",
     "one row per institution (anything in the program-cell base or graduate enrollment, 2020-2023)"),
]

file_rows = {}
file_cols = {}
for name, sql, grain in EXPORTS:
    df = q(sql)
    # AWLEVEL stays an integer even when nullable; booleans as true/false
    path = TAB / f"{name}.csv"
    df.to_csv(path, index=False, float_format="%.10g", na_rep="")
    file_rows[name] = len(df)
    file_cols[name] = list(df.columns)
    missing = [c for c in df.columns if c not in D]
    assert not missing, (name, missing)

# internal unsuppressed program file (NOT in tableau_ready)
internal = q("select year, unitid, instnm, stabbr, control_label, cipcode, cip_title, cip2, cip2_title, awlevel as award_level_code, "
             "level_key, completions, completions_men, completions_women, imputation_flag "
             "from m_program_cells order by year, unitid, awlevel, cipcode")
internal.to_csv(OUT / "INTERNAL_program_cells_unsuppressed.csv", index=False)
file_rows["unsuppressed program cells, local only, git-ignored (outputs)"] = len(internal)

# ---------------------------------------------------------------- privacy audit of tableau_ready
audit = {}
pc = pd.read_csv(TAB / "program_completions_by_year.csv", dtype={"cipcode": str, "cip2": str})
audit["program_file_rows_with_display_count_below_10"] = int((pc["display_count"] < 10).sum())
audit["program_file_suppressed_rows_with_nonblank_count"] = int(((pc["suppressed"] == 1) & pc["display_count"].notna()).sum())
audit["program_file_unsuppressed_rows_with_blank_count"] = int(((pc["suppressed"] == 0) & pc["display_count"].isna()).sum())
isum = pd.read_csv(TAB / "institution_summary.csv")
audit["institution_summary_completions_total_below_10"] = int((isum["completions_total"] < 10).sum())
audit["institution_summary_prior_or_2020_below_10"] = int(((isum["completions_prior_year"] < 10) | (isum["completions_2020"] < 10)).sum())
fs = pd.read_csv(TAB / "field_summary.csv", dtype={"cip2": str})
audit["field_summary_completions_total_below_10"] = int((fs["completions_total"] < 10).sum())
audit["tableau_ready_files_with_men_or_women_columns"] = int(sum(any(re.search(r"(^|_)(men|women)($|_)", c) for c in cols) for cols in file_cols.values()))
assert audit["program_file_rows_with_display_count_below_10"] == 0
assert audit["program_file_suppressed_rows_with_nonblank_count"] == 0
assert audit["institution_summary_completions_total_below_10"] == 0
assert audit["field_summary_completions_total_below_10"] == 0

# ---------------------------------------------------------------- data dictionary README
lines = ["# tableau_ready data dictionary", "",
         f"Generated by `{SCRIPT}` on {dt.datetime.now():%Y-%m-%d %H:%M}. Flat CSVs, UTF-8, snake_case, empty cell = null. "
         "All files cover IPEDS file years 2020-2023 (completions final/revised `_RV` release; enrollment fall 2020-2023, "
         "fall 2023 provisional). 2024 completions are PROVISIONAL and are not used.", "",
         "Base: completions with MAJORNUM = 1 (first majors), CIPCODE <> 99 (no total rows), AWLEVEL 7, 17, 18, 19. "
         "A program cell = institution x CIP6 x award level x year. Counts are degrees/awards, not students.", "",
         "Suppression: primary threshold 10 (count < 10 hidden, zero counts included) plus two complementary passes "
         "(see `measure_definitions.md`). No program-level count below 10 appears in any file here; the unsuppressed "
         "program file is written to a git-ignored local file under `outputs/` and must not be published.", "",
         "Ratios named `ratio_*` are completions divided by graduate enrollment. They are NOT cohort completion or graduation rates.",
         "Percent columns (`yoy_pct_change`, `pct_change_vs_2020`) are in percent units (4.2 = +4.2%).", ""]
for name, sql, grain in EXPORTS:
    lines += [f"## {name}.csv", "", f"Grain: {grain}. Rows: {file_rows[name]:,}.", "",
              "| column | description |", "|---|---|"]
    for c in file_cols[name]:
        lines.append(f"| {c} | {D[c].replace('|', '/')} |")
    lines.append("")
(TAB / "README_data_dictionary.md").write_text("\n".join(lines), encoding="utf-8")

# ---------------------------------------------------------------- measure definitions
defs = f"""# Measure definitions

Generated by `{SCRIPT}` (SQL in `sql/`). Source tables: `completions` (2020-2023 final/revised), `enrollment`, `institutions`, `cip_titles`, `nsf_sed_median_years` in `data/ipeds.duckdb`.

## Analysis base
- Award levels: AWLEVEL 7 master's, 17 doctor's research/scholarship, 18 doctor's professional practice, 19 doctor's other. `all_masters_doctoral` = 7 + 17 + 18 + 19.
- MAJORNUM = 1 only (first majors; second majors excluded) and CIPCODE <> '99' (99 = total row, excluded to avoid double counting).
- Program cell = institution (UNITID) x 6-digit CIP x award level x year. A cell is a row of the completions file; cells with 0 completions are kept in the base (they are reported rows) and count as below every threshold.
- Institution name/state/control/Carnegie come from the HD file of the same year; CIP titles from CIP 2020 (cip_titles); 2-digit family = first two characters of the CIP code.
- Year = IPEDS file year. Completions year Y covers academic year Y-1 to Y (2023 = 2022-23). Enrollment year Y is fall Y (fall 2023 is the term AFTER the 2022-23 awards).

## Measures
- **completions** = ctotalt (total of men + women) summed over the grain.
- **grad_enrollment_total / ft / pt** = fall EFALEVEL 12 / 32 / 52 total headcount (EFTOTLT) per institution. Enrollment has no CIP or award-level detail in this file, so enrollment and any ratio exist at institution level and national level only, never by CIP family or by individual award level.
- **ratio_completions_to_grad_enrollment** = (master's + all doctoral completions in year Y) / (fall graduate enrollment in the same IPEDS file year Y). This is strictly a RATIO of two annual counts; it is NOT a cohort completion rate or graduation rate (the numerator students are not the denominator students; the denominator also includes post-baccalaureate and post-master's certificate students and excludes nothing for program length; professional doctorates take 3-4 years, master's 1-2). A second variant divides by the PRIOR fall enrollment (fall Y-1, the start of the same academic year); the two variants bracket the timing problem.
- **national matched ratio** = same ratio summed over institutions that have graduate enrollment > 0 (the all-level completions total is 0 where an institution has no master's/doctoral cells); `*_all` variants use all completions over all enrollment.
- **yoy_pct_change** = (value_Y - value_(Y-1)) / value_(Y-1) x 100; **pct_change_vs_2020** = (value_Y - value_2020) / value_2020 x 100. Every percentage is accompanied by program-cell counts (and institution counts at national/field grain) for the current, prior and 2020 values. Institution-level changes compare institution totals, so they mix new/closed programs with growth; the cell counts show this. They are empty if either side is suppressed or the base is 0/missing.

## Small-cell suppression
- Primary: a program cell is suppressed if completions < threshold (5, 10 or 20). Display files use 10.
- Pass 1 (complementary, family): within institution x award level x year x CIP2 family, if exactly one cell is primary-suppressed, the next-smallest remaining cell (ties by CIP code) is also suppressed. If the family has no remaining cell, nothing more can be done at this step.
- Pass 2 (complementary, institution): institution totals by level are published, so within institution x award level x year, if exactly one cell is suppressed after pass 1, the next-smallest remaining cell is also suppressed. Afterwards no institution x level x year group has exactly one suppressed cell unless it has a single program cell, whose total is itself < 10 and therefore suppressed.
- Totals: institution totals < 10 are suppressed; the all-level institution total is also suppressed if exactly one level row is suppressed (otherwise subtraction would reveal it). Field/national totals < 10 are suppressed.
- Limitation: this is a simple rule, not an optimal secondary-suppression algorithm. Two hidden cells in a group still have a published combined total when the level total is shown; each is below the threshold. Suppressed cells are also not distinguishable from missing programs in the display file except via the `suppressed` flag.
- Suppression statistics (suppression_impact.csv): share of cells/completions under threshold, institutions with at least one suppressed cell, institutions where every cell is suppressed, and extra complementary cells, for every threshold x level x year.

## SED benchmark
- NSF Survey of Earned Doctorates Table 1-12 (median years to research doctorate by trend broad field), latest year of two cycles: nsf26326 (newest, 2025) and nsf25349 (2024). The grids do not share a calendar year. The CIP2 -> SED broad field mapping in field_summary is an approximate mapping made by the author (not official) and only meaningful for research doctorates.
"""
(OUT / "measure_definitions.md").write_text(defs, encoding="utf-8")

# ---------------------------------------------------------------- key numbers
KN = {}


def kn(key, value, output_file, definition):
    if hasattr(value, "item"):
        value = value.item()
    KN[key] = {"value": value, "script": SCRIPT, "output_file": output_file, "definition": definition}


imp = q("select * from m_supp_impact")
imp_f = "tableau_ready/suppression_impact.csv"
for r in imp[imp.year == 2023].itertuples():
    base = f"supp_{r.level_key}_2023_t{r.threshold}"
    dfn = f"{r.level_key} program cells in 2023 (final), threshold {r.threshold}: "
    kn(f"{base}_n_cells", int(r.n_cells), imp_f, dfn + "number of program cells (MAJORNUM 1, CIP<>99)")
    kn(f"{base}_share_cells_lt_threshold", float(r.share_cells_primary_suppressed), imp_f, dfn + "share of cells with count < threshold")
    kn(f"{base}_n_cells_lt_threshold", int(r.n_cells_primary_suppressed), imp_f, dfn + "cells with count < threshold")
    kn(f"{base}_share_completions_in_lt_threshold_cells", float(r.share_completions_in_primary_suppressed), imp_f,
       dfn + "share of completions that sit in cells below threshold")
    kn(f"{base}_n_institutions_with_suppressed", int(r.n_institutions_with_primary_suppressed), imp_f,
       dfn + "institutions with at least one cell below threshold")
    kn(f"{base}_n_institutions", int(r.n_institutions), imp_f, dfn + "institutions with at least one cell")
    kn(f"{base}_share_institutions_all_cells_suppressed", float(r.share_institutions_all_cells_primary_suppressed), imp_f,
       dfn + "share of institutions whose every program cell is below threshold")
    kn(f"{base}_n_complementary_cells", int(r.n_cells_complementary_family + r.n_cells_complementary_institution), imp_f,
       dfn + "extra cells hidden by complementary suppression (pass 1 + pass 2)")
    kn(f"{base}_n_complementary_family_pass", int(r.n_cells_complementary_family), imp_f, dfn + "extra cells from pass 1 (family)")
    kn(f"{base}_n_complementary_institution_pass", int(r.n_cells_complementary_institution), imp_f, dfn + "extra cells from pass 2 (institution)")
    kn(f"{base}_share_cells_suppressed_total", float(r.share_cells_suppressed_total), imp_f, dfn + "share of cells hidden incl. complementary")

nat = q("select * from m_national_display")
nat_f = "tableau_ready/national_totals.csv"
for r in nat.itertuples():
    b = f"national_{r.level_key}_{r.year}"
    kn(f"{b}_completions", int(r.completions_total), nat_f, f"{r.level_key} completions in {r.year} (MAJORNUM 1, CIP<>99, IPEDS final)")
    kn(f"{b}_n_program_cells", int(r.n_program_cells), nat_f, f"{r.level_key} program cells in {r.year}")
    kn(f"{b}_n_institutions", int(r.n_institutions), nat_f, f"{r.level_key} institutions with at least one cell in {r.year}")
    if r.year > 2020:
        kn(f"{b}_yoy_pct", float(r.yoy_pct_change), nat_f,
           f"{r.level_key} percent change in completions {r.year - 1}->{r.year}; cells {int(r.n_program_cells_prior_year)} -> {int(r.n_program_cells)}")
        kn(f"{b}_pct_vs_2020", float(r.pct_change_vs_2020), nat_f,
           f"{r.level_key} percent change in completions 2020->{r.year}; cells {int(r.n_program_cells_2020)} -> {int(r.n_program_cells)}")
    if r.level_key == "all_masters_doctoral":
        kn(f"{b}_grad_enrollment_total", int(r.grad_enrollment_total), nat_f, f"fall {r.year} graduate enrollment EFALEVEL 12, {int(r.n_institutions_with_enrollment)} institutions")
        kn(f"{b}_ratio_matched", float(r.ratio_completions_to_grad_enrollment_matched), nat_f,
           f"ratio (NOT a completion rate) of master's+doctoral completions to graduate enrollment in {r.year}, matched institutions ({int(r.n_matched_institutions)})")
        kn(f"{b}_ratio_all", float(r.ratio_completions_to_grad_enrollment_all), nat_f,
           f"ratio of all master's+doctoral completions to all graduate enrollment in {r.year}")
        if r.year > 2020:
            kn(f"{b}_ratio_prior_fall_matched", float(r.ratio_completions_to_prior_fall_grad_enrollment_matched), nat_f,
               f"ratio of year-{r.year} completions to fall-{r.year - 1} graduate enrollment, {int(r.n_matched_institutions_prior_fall)} institutions")

qs = q("""select
  count(*) filter (where grad_enrollment_total > 0 and completions >= 10 and year = 2023) as n,
  quantile_cont(completions * 1.0 / grad_enrollment_total, 0.1) filter (where grad_enrollment_total > 0 and completions >= 10 and year = 2023) as p10,
  quantile_cont(completions * 1.0 / grad_enrollment_total, 0.5) filter (where grad_enrollment_total > 0 and completions >= 10 and year = 2023) as p50,
  quantile_cont(completions * 1.0 / grad_enrollment_total, 0.9) filter (where grad_enrollment_total > 0 and completions >= 10 and year = 2023) as p90,
  count(*) filter (where grad_enrollment_total > 0 and completions * 1.0 / grad_enrollment_total > 1 and completions >= 10 and year = 2023) as n_gt1
  from m_inst_summary_internal where level_key = 'all_masters_doctoral'""").iloc[0]
isf = "tableau_ready/institution_summary.csv"
kn("institution_ratio_2023_n_institutions", int(qs.n), isf, "institutions with 2023 completions total >= 10 and graduate enrollment > 0 [computed on the unsuppressed institution table, not the published institution_summary.csv, which displays fewer ratios]")
kn("institution_ratio_2023_p10", float(qs.p10), isf, "10th percentile of institution ratio (completions/fall-2023 grad enrollment), those institutions")
kn("institution_ratio_2023_median", float(qs.p50), isf, "median institution ratio, same institutions")
kn("institution_ratio_2023_p90", float(qs.p90), isf, "90th percentile institution ratio, same institutions")
kn("institution_ratio_2023_n_above_1", int(qs.n_gt1), isf, "institutions where 2023 completions exceed fall-2023 graduate enrollment (ratio > 1)")

top = q("select cip2, cip2_title, completions from m_field_internal where year = 2023 and level_key = 'masters' order by completions desc limit 5")
kn("top5_cip2_masters_2023", [{"cip2": r.cip2, "title": r.cip2_title, "completions": int(r.completions)} for r in top.itertuples()],
   "tableau_ready/field_summary.csv", "five CIP2 families with the most master's completions in 2023")

sed = q("select cycle, sed_year, measure, median_years from m_sed_benchmark where field = 'All fields'")
for r in sed.itertuples():
    kn(f"sed_all_fields_{r.cycle}_{r.sed_year}_{r.measure.replace(' ', '_').replace(chr(39), '')}", float(r.median_years),
       "tableau_ready/sed_benchmark.csv", f"NSF SED Table 1-12 All fields median years, {r.measure}, cycle {r.cycle}, year {r.sed_year}")

prov = q("""select count(*) n, avg((ctotalt < 10)::int) s10 from completions_2024_provisional
            where majornum = 1 and cipcode <> '99' and awlevel = 7""").iloc[0]
kn("masters_2024_provisional_n_cells", int(prov.n), "outputs/measures_log.md", "PROVISIONAL 2024 master's cells (context only, not final)")
kn("masters_2024_provisional_share_lt10", float(prov.s10), "outputs/measures_log.md", "PROVISIONAL 2024 master's share of cells below 10 (context only)")
for k, v in checks.items():
    if isinstance(v, (int, float)):
        kn(f"check_{k}", v, "outputs/measures_log.md", f"build check: {k}")
for name, n in file_rows.items():
    kn(f"rows_{re.sub('[^a-z0-9]+', '_', name.lower()).strip('_')}", n, "tableau_ready/", f"row count of {name}")

meta = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
        "note": "Every value was computed by the named script from data/ipeds.duckdb. 03_reconcile.py appends reconciliation keys (prefix recon_)."}
(OUT / "key_numbers.json").write_text(json.dumps({"_meta": meta, "numbers": KN}, indent=2), encoding="utf-8")

# ---------------------------------------------------------------- measures_log.md
def md(df):
    return df.to_markdown(index=False) if hasattr(df, "to_markdown") else df.to_string(index=False)


try:
    import tabulate  # noqa: F401
    HAVE_TAB = True
except ImportError:
    HAVE_TAB = False


def table(df):
    if HAVE_TAB:
        return df.to_markdown(index=False)
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        out.append("| " + " | ".join("" if pd.isna(v) else (f"{v:,}" if isinstance(v, int) else str(v)) for v in row) + " |")
    return "\n".join(out)


L = [f"# Measures build log", "", f"Generated by `{SCRIPT}` on {dt.datetime.now():%Y-%m-%d %H:%M}. Everything below was computed in this run.", "",
     "## Build checks", ""]
for k, v in checks.items():
    L.append(f"- {k}: {v:,}" if isinstance(v, int) else f"- {k}: {v}")
L += ["", "## Privacy audit of tableau_ready (must be 0)", ""]
L += [f"- {k}: {v}" for k, v in audit.items()]
L += ["", "## Rows per output", ""] + [f"- {k}: {v:,}" for k, v in file_rows.items()]

h = imp[(imp.threshold == 10) & (imp.level_key.isin(["masters", "research_doctorate", "professional_doctorate", "other_doctorate"]))][
    ["year", "level_key", "n_cells", "n_cells_primary_suppressed", "share_cells_primary_suppressed", "share_completions_in_primary_suppressed",
     "n_institutions", "n_institutions_with_primary_suppressed", "share_institutions_all_cells_primary_suppressed"]].copy()
h["share_cells_primary_suppressed"] = h["share_cells_primary_suppressed"].round(4)
h["share_completions_in_primary_suppressed"] = h["share_completions_in_primary_suppressed"].round(4)
h["share_institutions_all_cells_primary_suppressed"] = h["share_institutions_all_cells_primary_suppressed"].round(4)
L += ["", "## Suppression at threshold 10 by level and year (primary)", "", table(h.sort_values(["level_key", "year"]))]
t23 = imp[(imp.year == 2023) & (imp.level_key == "masters")][
    ["threshold", "n_cells", "n_cells_primary_suppressed", "share_cells_primary_suppressed", "share_completions_in_primary_suppressed",
     "n_cells_complementary_family", "n_cells_complementary_institution", "n_institutions_with_primary_suppressed",
     "share_institutions_all_cells_primary_suppressed"]].copy()
for c in ["share_cells_primary_suppressed", "share_completions_in_primary_suppressed", "share_institutions_all_cells_primary_suppressed"]:
    t23[c] = t23[c].round(4)
L += ["", "## 2023 master's by threshold", "", table(t23)]
a23 = imp[(imp.year == 2023) & (imp.level_key == "all_masters_doctoral")][
    ["threshold", "n_cells", "n_cells_primary_suppressed", "n_cells_complementary_family", "n_cells_complementary_institution",
     "n_cells_suppressed_total"]]
L += ["", "## 2023 all levels: complementary suppression extra cells", "", table(a23)]
L += ["", "## Notes and flags", "",
      "- 2023 master's check: user expectation was ~42,371 rows and ~58.8% of cells under 10. This build (final `_RV` data) gives "
      f"{KN['supp_masters_2023_t10_n_cells']['value']:,} cells and {KN['supp_masters_2023_t10_share_cells_lt_threshold']['value']:.4%} under 10. "
      "See reconciliation.md for the same numbers recomputed from the original (non-RV) C2023_a.csv.",
      f"- 2024 provisional master's (context only): {KN['masters_2024_provisional_n_cells']['value']:,} cells, "
      f"{KN['masters_2024_provisional_share_lt10']['value']:.4%} under 10.",
      "- Zero-count cells are part of the base (reported rows) and count as below every threshold; see check zero_count_cells.",
      "- Enrollment is institution-level only; ratios are labelled ratios, not cohort completion rates. Fall-2023 enrollment is the term after the 2022-23 awards, so a prior-fall variant is also provided.",
      "- Suppression is a simple two-pass rule (see measure_definitions.md); residual group counts are in the checks above.",
      "- CIP2 -> SED broad field mapping is an approximate mapping made by the author, flagged as such in the CSV column name."]
(OUT / "measures_log.md").write_text("\n".join(L) + "\n", encoding="utf-8")
con.close()
print("done", {k: v for k, v in file_rows.items()})
print(json.dumps(checks, indent=1))
print(json.dumps(audit, indent=1))
