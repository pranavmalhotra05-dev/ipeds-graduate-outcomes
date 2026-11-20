"""03_reconcile.py - independent reconciliation of the DuckDB measures against the raw zipped CSVs and published figures.

(a) award-level totals recomputed with pandas straight from the raw zips vs DuckDB-derived numbers (exact match required)
(b) institution totals of detail rows vs the CSV's own CIPCODE=99 total rows
(c) national totals vs NCES Digest Table 318.10 (hard-coded published figures, URL and retrieval date below)
(d) research doctorates vs NSF SED headline total (published figure below)
Writes outputs/reconciliation.md and outputs/reconciliation.json and appends recon_* keys to outputs/key_numbers.json.

Run after 02_build_measures.py:  python -I src/03_reconcile.py
"""
import datetime as dt
import io
import json
import zipfile
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
OUT = ROOT / "outputs"
SCRIPT = "src/03_reconcile.py"
LEVELS = {7: "masters", 17: "research_doctorate", 18: "professional_doctorate", 19: "other_doctorate"}
FINAL_MEMBERS = {2020: "c2020_a_rv.csv", 2021: "c2021_a_rv.csv", 2022: "c2022_a_rv.csv", 2023: "C2023_a_RV.csv"}
ORIG_MEMBERS = {2020: "c2020_a.csv", 2021: "c2021_a.csv", 2022: "c2022_a.csv", 2023: "C2023_a.csv"}

# published figures (retrieved 2026-11-20 via web fetch of the cited pages)
DIGEST_URL = "https://nces.ed.gov/programs/digest/d23/tables/dt23_318.10.asp"
DIGEST = {  # Table 318.10, Digest of Education Statistics 2023; academic year ending in key; 2022-23 is PROJECTED there
    2020: {"masters": 843531, "doctors": 190133, "projected": False},
    2021: {"masters": 866932, "doctors": 194052, "projected": False},
    2022: {"masters": 880249, "doctors": 203884, "projected": False},
    2023: {"masters": 881580, "doctors": 202258, "projected": True},
}
SED_URL = "https://ncses.nsf.gov/surveys/earned-doctorates/2023"
SED_2023_TOTAL = 57862          # "Of the 57,862 new research doctorates granted in 2023" (NCSES SED 2023 page)
SED_2023_REVISED = 57806        # later-revised 2023 figure reported in the 2024 release (per NCSES search result; not fetched in full)
SED_2022_TOTAL = 57448          # as reported by NCSES search summary
TOL_DIGEST = 0.03               # judged tolerance, see notes

con = duckdb.connect(str(ROOT / "data" / "ipeds.duckdb"), read_only=True)


def read_member(year, member):
    zf = zipfile.ZipFile(RAW / f"C{year}_A.zip")
    names = {n.lower(): n for n in zf.namelist()}
    raw = zf.read(names[member.lower()])
    for enc in ("utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(io.BytesIO(raw), dtype=str, encoding=enc, low_memory=False)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [c.strip().upper() for c in df.columns]
    df = df[["UNITID", "CIPCODE", "MAJORNUM", "AWLEVEL", "CTOTALT"]].copy()
    for c in df.columns:
        df[c] = df[c].str.strip()
    for c in ("UNITID", "MAJORNUM", "AWLEVEL", "CTOTALT"):
        df[c] = pd.to_numeric(df[c], errors="raise").astype("int64")
    return df


def summarize(df):
    d = df[(df.MAJORNUM == 1) & (df.CIPCODE != "99") & (df.AWLEVEL.isin(LEVELS))]
    out = {}
    for lv, name in list(LEVELS.items()) + [(None, "all_masters_doctoral")]:
        x = d if lv is None else d[d.AWLEVEL == lv]
        out[name] = {"rows": int(len(x)), "institutions": int(x.UNITID.nunique()), "completions": int(x.CTOTALT.sum()),
                     "cells_lt10": int((x.CTOTALT < 10).sum()),
                     "share_lt10": float((x.CTOTALT < 10).mean())}
    return out


res = {"generated": dt.datetime.now().isoformat(timespec="seconds"), "a_award_level_totals": {}, "b_total_rows": {},
       "c_digest": {}, "d_sed": {}, "c_digest_source": DIGEST_URL, "d_sed_source": SED_URL}
mismatch_count = 0
raw_frames = {}
orig_summary = {}
for y, m in FINAL_MEMBERS.items():
    df = read_member(y, m)
    raw_frames[y] = df
    s = summarize(df)
    duck = con.execute(f"""
      select level_key, count(*) rows, count(distinct unitid) inst, sum(completions) comp, sum((completions<10)::int) lt10
      from m_program_cells where year = {y} group by level_key""").df().set_index("level_key")
    duck_all = con.execute(f"""select count(*) rows, count(distinct unitid) inst, sum(completions) comp, sum((completions<10)::int) lt10
                               from m_program_cells where year = {y}""").df().iloc[0]
    supp = con.execute(f"select level_key, n_cells_primary_suppressed from m_supp_impact where threshold = 10 and year = {y}").df().set_index("level_key")
    res["a_award_level_totals"][y] = {}
    for name, v in s.items():
        if name == "all_masters_doctoral":
            d = {"rows": int(duck_all.rows), "institutions": int(duck_all.inst), "completions": int(duck_all.comp), "cells_lt10": int(duck_all.lt10)}
        else:
            r = duck.loc[name]
            d = {"rows": int(r.rows), "institutions": int(r.inst), "completions": int(r.comp), "cells_lt10": int(r.lt10)}
        impact_lt10 = int(supp.loc[name, "n_cells_primary_suppressed"])
        ok = all(v[k] == d[k] for k in d) and impact_lt10 == v["cells_lt10"]
        mismatch_count += 0 if ok else 1
        res["a_award_level_totals"][y][name] = {"pandas_from_raw": v, "duckdb": d, "suppression_impact_lt10_cells": impact_lt10, "exact_match": bool(ok)}
    # original (non-RV) file for the same year
    o = read_member(y, ORIG_MEMBERS[y])
    orig_summary[y] = {"raw_rows_all": int(len(o)), **summarize(o)}
res["a_all_exact_match"] = mismatch_count == 0
res["a_mismatch_count"] = mismatch_count

# original vs final/revised, master's
res["a_original_vs_revised_masters"] = {}
for y in FINAL_MEMBERS:
    f = res["a_award_level_totals"][y]["masters"]["pandas_from_raw"]
    o = orig_summary[y]["masters"]
    res["a_original_vs_revised_masters"][y] = {"original": o, "revised": f}

# (b) CIPCODE = 99 total rows vs detail sums
res["b_total_rows"] = {}
for y, df in raw_frames.items():
    lv = df[(df.MAJORNUM == 1) & df.AWLEVEL.isin(LEVELS)]
    tot = lv[lv.CIPCODE == "99"].groupby(["UNITID", "AWLEVEL"]).CTOTALT.sum().rename("total_row")
    det = lv[lv.CIPCODE != "99"].groupby(["UNITID", "AWLEVEL"]).CTOTALT.sum().rename("detail_sum")
    j = pd.concat([tot, det], axis=1)
    both = j.dropna()
    diff = both[both.total_row != both.detail_sum]
    res["b_total_rows"][y] = {
        "institution_levels_with_total_row": int(j.total_row.notna().sum()),
        "institution_levels_with_detail": int(j.detail_sum.notna().sum()),
        "total_row_without_detail": int(j.detail_sum.isna().sum()),
        "detail_without_total_row": int(j.total_row.isna().sum()),
        "compared": int(len(both)), "mismatches": int(len(diff)),
        "sum_total_rows": int(j.total_row.sum()), "sum_detail_rows": int(j.detail_sum.sum()),
        "mismatch_examples": [{"unitid": int(i[0]), "awlevel": int(i[1]), "total_row": int(r.total_row), "detail_sum": int(r.detail_sum)}
                              for i, r in diff.head(10).iterrows()],
    }
    duck_sum = con.execute(f"select sum(completions) from m_program_cells where year = {y}").fetchone()[0]
    res["b_total_rows"][y]["duckdb_detail_sum"] = int(duck_sum)
    res["b_total_rows"][y]["duckdb_equals_raw_detail"] = int(duck_sum) == int(j.detail_sum.sum())

# (c) Digest comparison
nat = con.execute("select year, level_key, completions_total from m_national_display").df()
res["c_digest"] = {}
for y, d in DIGEST.items():
    ipeds_m = int(nat[(nat.year == y) & (nat.level_key == "masters")].completions_total.iloc[0])
    ipeds_d = int(nat[(nat.year == y) & (nat.level_key.isin(["research_doctorate", "professional_doctorate", "other_doctorate"]))].completions_total.sum())
    res["c_digest"][y] = {
        "digest_masters": d["masters"], "ipeds_masters_first_majors": ipeds_m,
        "masters_diff_pct": (ipeds_m - d["masters"]) * 100.0 / d["masters"],
        "digest_doctors": d["doctors"], "ipeds_doctors_17_18_19_first_majors": ipeds_d,
        "doctors_diff_pct": (ipeds_d - d["doctors"]) * 100.0 / d["doctors"],
        "digest_value_is_projected": d["projected"],
        "within_tolerance_3pct": abs((ipeds_m - d["masters"]) / d["masters"]) <= TOL_DIGEST and abs((ipeds_d - d["doctors"]) / d["doctors"]) <= TOL_DIGEST,
    }

# 2023 master's growth drivers (surprise check)
drv = con.execute("""
  with a as (select unitid, any_value(instnm) n, sum(completions) c from m_program_cells where year = 2023 and awlevel = 7 group by unitid),
       b as (select unitid, sum(completions) c from m_program_cells where year = 2022 and awlevel = 7 group by unitid)
  select a.unitid, a.n as instnm, a.c as c2023, coalesce(b.c, 0) as c2022, a.c - coalesce(b.c, 0) as change
  from a left join b using (unitid) order by change desc limit 10""").df()
res["c_masters_2023_top_gainers"] = drv.to_dict("records")
tot_change = con.execute("""select (select sum(completions) from m_program_cells where year=2023 and awlevel=7)
                                  - (select sum(completions) from m_program_cells where year=2022 and awlevel=7)""").fetchone()[0]
res["c_masters_2023_total_change"] = int(tot_change)
res["c_masters_2023_top10_gain_share"] = float(drv.change.sum() / tot_change)
fam = con.execute("""
  with a as (select cip2, any_value(cip2_title) t, sum(completions) c from m_program_cells where year = 2023 and awlevel = 7 group by cip2),
       b as (select cip2, sum(completions) c from m_program_cells where year = 2022 and awlevel = 7 group by cip2)
  select a.cip2, a.t, a.c - coalesce(b.c, 0) as change from a left join b using (cip2) order by change desc limit 5""").df()
res["c_masters_2023_top_family_gains"] = fam.to_dict("records")

# (d) SED
ipeds_17 = int(nat[(nat.year == 2023) & (nat.level_key == "research_doctorate")].completions_total.iloc[0])
ipeds_17_22 = int(nat[(nat.year == 2022) & (nat.level_key == "research_doctorate")].completions_total.iloc[0])
fam17 = con.execute("""select cip2, any_value(cip2_title) t, sum(completions) c from m_program_cells
                       where year = 2023 and awlevel = 17 group by cip2 order by c desc limit 6""").df()
res["d_sed"] = {"sed_2023_total_research_doctorates": SED_2023_TOTAL, "sed_2023_revised_total_per_later_release": SED_2023_REVISED,
                "sed_2022_total": SED_2022_TOTAL,
                "ipeds_awlevel17_2023_first_majors": ipeds_17, "ipeds_awlevel17_2022_first_majors": ipeds_17_22,
                "ipeds_minus_sed_2023": ipeds_17 - SED_2023_TOTAL, "ipeds_over_sed_2023_ratio": ipeds_17 / SED_2023_TOTAL,
                "ipeds_over_sed_2022_ratio": ipeds_17_22 / SED_2022_TOTAL,
                "ipeds_awlevel17_2023_top_cip2": fam17.to_dict("records"),
                "match": False}

# ---------------------------------------------------------------- write outputs
(OUT / "reconciliation.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")


def pct(x):
    return f"{x:.4%}"


L = ["# Reconciliation", "", f"Generated by `{SCRIPT}` on {dt.datetime.now():%Y-%m-%d %H:%M}. Machine-readable copy: `reconciliation.json`.", "",
     "## (a) Award-level totals: raw zipped CSVs (pandas) vs DuckDB-derived", "",
     "Filters: MAJORNUM = 1, CIPCODE <> 99, AWLEVEL in 7/17/18/19, final/revised `_rv` member. Compared per level and year: rows, distinct institutions, completions, cells under 10 (also vs `m_supp_impact` at threshold 10).", "",
     f"**Exact match in all {sum(len(v) for v in res['a_award_level_totals'].values())} level-year checks: {res['a_all_exact_match']}** (mismatches: {mismatch_count}).", "",
     "| year | level | rows | institutions | completions | cells <10 | share <10 | exact match |", "|---|---|---|---|---|---|---|---|"]
for y, lv in res["a_award_level_totals"].items():
    for n, v in lv.items():
        p = v["pandas_from_raw"]
        L.append(f"| {y} | {n} | {p['rows']:,} | {p['institutions']:,} | {p['completions']:,} | {p['cells_lt10']:,} | {pct(p['share_lt10'])} | {v['exact_match']} |")
L += ["", "### 2023 master's: original (provisional-release) file vs final/revised file", "",
      "| year | original rows | revised rows | original completions | revised completions | original share <10 | revised share <10 |", "|---|---|---|---|---|---|---|"]
for y, v in res["a_original_vs_revised_masters"].items():
    o, f = v["original"], v["revised"]
    L.append(f"| {y} | {o['rows']:,} | {f['rows']:,} | {o['completions']:,} | {f['completions']:,} | {pct(o['share_lt10'])} | {pct(f['share_lt10'])} |")
L += ["", "The table above shows what each release gives; the revised file is used everywhere.", "",
      "## (b) Detail rows vs the file's own CIPCODE = 99 total rows (MAJORNUM 1, per institution x award level)", "",
      "| year | inst-levels with total row | with detail | compared | mismatches | total rows w/o detail | detail w/o total row | sum total rows | sum detail rows | DuckDB detail sum = raw detail |",
      "|---|---|---|---|---|---|---|---|---|---|"]
for y, v in res["b_total_rows"].items():
    L.append(f"| {y} | {v['institution_levels_with_total_row']:,} | {v['institution_levels_with_detail']:,} | {v['compared']:,} | {v['mismatches']:,} | "
             f"{v['total_row_without_detail']:,} | {v['detail_without_total_row']:,} | {v['sum_total_rows']:,} | {v['sum_detail_rows']:,} | {v['duckdb_equals_raw_detail']} |")
for y, v in res["b_total_rows"].items():
    if v["mismatch_examples"]:
        L += ["", f"Mismatch examples {y} (first 10): " + "; ".join(f"unitid {e['unitid']} awlevel {e['awlevel']} total {e['total_row']} vs detail {e['detail_sum']}" for e in v["mismatch_examples"])]
L += ["", "## (c) National totals vs NCES Digest of Education Statistics, Table 318.10", "",
      f"Source: {DIGEST_URL} (Digest 2023 edition, retrieved 2026-11-20). Digest counts are degrees conferred from IPEDS completions (all degrees, Title IV institutions) and the table notes do not say first majors only; our figures are first majors only (MAJORNUM 1). The Digest 2022-23 row is labelled PROJECTED (footnote 3), so it is not an actual published count; no later Digest edition (d24) table was reachable (HTTP 404). Digest doctor's = research + professional + other (includes former first-professional). Judged tolerance: +/-3%. IPEDS first-major counts run about 1.0-1.6% above the Digest in every actual year; the reason (e.g. Digest definition or imputation differences) was not verified.", "",
      "| year (AY ending) | Digest master's | IPEDS master's (this project) | diff % | Digest doctor's | IPEDS 17+18+19 | diff % | Digest value projected | within 3% |", "|---|---|---|---|---|---|---|---|---|"]
for y, v in res["c_digest"].items():
    L.append(f"| {y} | {v['digest_masters']:,} | {v['ipeds_masters_first_majors']:,} | {v['masters_diff_pct']:+.2f}% | {v['digest_doctors']:,} | "
             f"{v['ipeds_doctors_17_18_19_first_majors']:,} | {v['doctors_diff_pct']:+.2f}% | {v['digest_value_is_projected']} | {v['within_tolerance_3pct']} |")
L += ["", "**Surprise:** IPEDS master's rise +5.98% in 2023 (947,728 vs 894,277), while the Digest (projected) shows +0.2%. The difference vs the Digest is 7.5% in 2023 against about 1.5% in 2020-2022. The revised file differs from the original by only 126 master's, so it is not a revision effect. "
      f"Total 2023 master's change is {res['c_masters_2023_total_change']:,}; the ten institutions with the largest gains account for {res['c_masters_2023_top10_gain_share']:.1%} of it:", ""]
L += ["| unitid | institution | 2022 | 2023 | change |", "|---|---|---|---|---|"]
for r in res["c_masters_2023_top_gainers"]:
    L.append(f"| {r['unitid']} | {r['instnm']} | {int(r['c2022']):,} | {int(r['c2023']):,} | {int(r['change']):+,} |")
L += ["", "Largest CIP2 families by master's gain 2022->2023: " + "; ".join(f"{r['cip2']} {r['t']} ({int(r['change']):+,})" for r in res["c_masters_2023_top_family_gains"]) + ".",
      "", "The Digest 2022-23 figure is a projection, so the 2023 gap may reflect the projection rather than an IPEDS anomaly; this was not resolved here.", "",
      "## (d) NSF Survey of Earned Doctorates headline vs IPEDS research doctorates (AWLEVEL 17)", "",
      f"Source: {SED_URL}: \"Of the 57,862 new research doctorates granted in 2023\".", "",
      f"- IPEDS AWLEVEL 17, first majors: 2023 = {ipeds_17:,}; 2022 = {ipeds_17_22:,}.",
      f"- IPEDS minus SED 2023 = {res['d_sed']['ipeds_minus_sed_2023']:,}; ratio {res['d_sed']['ipeds_over_sed_2023_ratio']:.3f} (2022: {res['d_sed']['ipeds_over_sed_2022_ratio']:.3f}).",
      "- These do NOT match. The two use different definitions (IPEDS AWLEVEL 17 is the institution's classification of doctor's degrees as research/scholarship, counted by program award; SED counts research doctorate recipients). The cause of the 40% gap was NOT investigated or explained here; do not present the two as comparable.",
      "- IPEDS AWLEVEL 17 2023 largest CIP2 families: " + "; ".join(f"{r['cip2']} {r['t']} ({int(r['c']):,})" for r in res["d_sed"]["ipeds_awlevel17_2023_top_cip2"]) + "."]
(OUT / "reconciliation.md").write_text("\n".join(L) + "\n", encoding="utf-8")

# append to key_numbers.json
kp = OUT / "key_numbers.json"
kj = json.loads(kp.read_text(encoding="utf-8"))
kj["numbers"] = {k: v for k, v in kj["numbers"].items() if not k.startswith("recon_")}


def kn(key, value, definition):
    kj["numbers"][key] = {"value": value, "script": SCRIPT, "output_file": "outputs/reconciliation.json", "definition": definition}


kn("recon_a_all_exact_match", res["a_all_exact_match"], "raw-CSV (pandas) vs DuckDB award-level totals, all years x levels, exact match")
for y, v in res["a_original_vs_revised_masters"].items():
    kn(f"recon_masters_{y}_original_file_rows", v["original"]["rows"], f"master's rows in the ORIGINAL {y} file (MAJORNUM 1, CIP<>99)")
    kn(f"recon_masters_{y}_original_file_share_lt10", v["original"]["share_lt10"], f"share of master's cells under 10 in the ORIGINAL {y} file")
    kn(f"recon_masters_{y}_revised_file_rows", v["revised"]["rows"], f"master's rows in the REVISED {y} file")
for y, v in res["b_total_rows"].items():
    kn(f"recon_b_{y}_total_row_mismatches", v["mismatches"], f"institution x level combos where detail sum differs from CIPCODE 99 row, {y}; compared {v['compared']}")
for y, v in res["c_digest"].items():
    kn(f"recon_digest_{y}_masters_diff_pct", v["masters_diff_pct"], f"IPEDS first-major master's vs Digest 318.10 master's (Digest projected: {v['digest_value_is_projected']})")
    kn(f"recon_digest_{y}_doctors_diff_pct", v["doctors_diff_pct"], f"IPEDS 17+18+19 vs Digest 318.10 doctor's")
kn("recon_sed_2023_total", SED_2023_TOTAL, f"NSF SED 2023 research doctorates, {SED_URL}")
kn("recon_ipeds_over_sed_2023_ratio", res["d_sed"]["ipeds_over_sed_2023_ratio"], "IPEDS AWLEVEL 17 2023 / SED 2023 total")
kn("recon_masters_2023_top10_gain_share", res["c_masters_2023_top10_gain_share"], "share of 2023 master's growth from 10 largest-gaining institutions")
kp.write_text(json.dumps(kj, indent=2), encoding="utf-8")
print("exact match:", res["a_all_exact_match"], "b mismatches:", {y: v["mismatches"] for y, v in res["b_total_rows"].items()})
