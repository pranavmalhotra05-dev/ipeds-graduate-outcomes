"""01_ingest.py - download IPEDS + NSF SED source files and build data/ipeds.duckdb.

Idempotent: zips/xlsx already in data_raw/ are not downloaded again; the DuckDB file and
outputs/ingest_log.md are rebuilt from scratch on every run.

Run:  python -I src/01_ingest.py
"""
import csv
import datetime as dt
import hashlib
import io
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import duckdb
import openpyxl
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data_raw"
DATA = ROOT / "data"
OUT = ROOT / "outputs"
for p in (RAW, DATA, OUT):
    p.mkdir(exist_ok=True)
DB = DATA / "ipeds.duckdb"
LOG = OUT / "ingest_log.md"

UA = {"User-Agent": "Mozilla/5.0 (research data ingest)"}
IPEDS = "https://nces.ed.gov/ipeds/datacenter/data/{}.zip"
YEARS = [2020, 2021, 2022, 2023]          # final-release years
TRY_EXTRA_COMPLETIONS = 2024               # included only if final (checked via dictionary)

log_lines = []


def L(s=""):
    log_lines.append(s)


def plain(s):
    """Plain ASCII-ish text for the log (no em/en dashes)."""
    return str(s).replace("\u2014", "-").replace("\u2013", "-").replace("\ufffd", "-")


# ---------------------------------------------------------------- download helpers
manifest = []          # dicts, becomes ingest_manifest
unavailable = []


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url, dest):
    """Download url to dest unless a valid copy exists. Returns True if file is available."""
    def valid(p):
        if not p.exists() or p.stat().st_size < 2000:
            return False
        if p.suffix == ".zip":
            return zipfile.is_zipfile(p)
        if p.suffix == ".xlsx":
            return zipfile.is_zipfile(p)
        if p.suffix == ".pdf":
            return p.read_bytes()[:4] == b"%PDF"
        return True
    if valid(dest):
        return True
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        unavailable.append((dest.name, url, f"HTTP {e.code}"))
        return False
    except Exception as e:  # network problem
        unavailable.append((dest.name, url, repr(e)))
        return False
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    if not valid(dest):
        dest.unlink()
        unavailable.append((dest.name, url, "downloaded content failed validation"))
        return False
    return True


def stamp(path):
    return dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")


def read_zip_csv(zpath, member):
    b = zipfile.ZipFile(zpath).read(member)
    try:
        t = b.decode("utf-8-sig")
        enc = "utf-8-sig"
    except UnicodeDecodeError:
        t = b.decode("cp1252")
        enc = "cp1252"
    df = pd.read_csv(io.StringIO(t), dtype=str, keep_default_na=False)
    df.columns = [c.strip().lstrip("﻿").upper() for c in df.columns]
    for c in df.columns:
        df[c] = df[c].str.strip()
    return df, enc


def members(zpath):
    return zipfile.ZipFile(zpath).infolist()


def note_manifest(zpath, url, used, note=""):
    zh = sha256(zpath)
    for info in members(zpath):
        rows = None
        status = "ok"
        if info.filename.lower().endswith(".csv"):
            with zipfile.ZipFile(zpath).open(info.filename) as f:
                rows = sum(1 for _ in f) - 1
        manifest.append(dict(
            file=info.filename, zip_file=zpath.name, url=url, rows=rows,
            bytes=zpath.stat().st_size, member_bytes=info.file_size, sha256=zh,
            downloaded_at=stamp(zpath), status=status,
            loaded=bool(used.get(info.filename)), note=note))


def num(series):
    """string -> numeric (NaN when blank/non-numeric)."""
    return pd.to_numeric(series.replace("", pd.NA), errors="coerce")


# ---------------------------------------------------------------- dictionaries
def dict_sheet(zpath, sheet):
    zf = zipfile.ZipFile(zpath)
    name = [n for n in zf.namelist() if n.lower().endswith(".xlsx")][0]
    wb = openpyxl.load_workbook(zf.open(name), read_only=True)
    names = {s.lower(): s for s in wb.sheetnames}
    rows = list(wb[names[sheet.lower()]].iter_rows(values_only=True))
    return rows


def dict_intro(zpath):
    rows = dict_sheet(zpath, "Introduction")
    return [plain(" | ".join(str(c) for c in r if c is not None))[:300] for r in rows[:6] if any(r)]


def dict_codes(zpath, sheet, varnames):
    rows = dict_sheet(zpath, sheet)
    hdr = [str(c).lower() for c in rows[0]]
    iv, ic, il = hdr.index("varname"), hdr.index("codevalue"), hdr.index("valuelabel")
    out = []
    for r in rows[1:]:
        if r[iv] in varnames:
            out.append((r[iv], str(r[ic]).strip(), str(r[il]).strip()))
    return out


# ================================================================ 1. DOWNLOADS
needed = {}
for y in YEARS + [TRY_EXTRA_COMPLETIONS]:
    needed[f"C{y}_A"] = IPEDS.format(f"C{y}_A")
for y in YEARS:
    needed[f"EF{y}A"] = IPEDS.format(f"EF{y}A")
for y in YEARS + [TRY_EXTRA_COMPLETIONS]:
    needed[f"HD{y}"] = IPEDS.format(f"HD{y}")
for d in ("C2023_A_Dict", "C2024_A_Dict", "EF2023A_Dict", "HD2023_Dict"):
    needed[d] = IPEDS.format(d)
# probes for files that may or may not exist (reported, not required)
probes = {"EF2024A": IPEDS.format("EF2024A")}

paths = {}
for k, url in {**needed, **probes}.items():
    p = RAW / f"{k}.zip"
    if fetch(url, p):
        paths[k] = p

# NSF SED Table 1-12 : try newest cycle first. Both cycles are kept (their year grids differ).
NSF_CYCLES = [
    ("nsf26326", "https://ncses.nsf.gov/pubs/nsf26326/assets/data-tables/tables/nsf26326-tab001-012"),
    ("nsf25349", "https://ncses.nsf.gov/pubs/nsf25349/assets/data-tables/tables/nsf25349-tab001-012"),
]
# also probe a few possible newer report numbers (cheap 404s)
for probe in ("nsf27", ):
    pass
nsf_paths = {}
for cyc, base in NSF_CYCLES:
    for ext in ("xlsx", "pdf"):
        p = RAW / f"{cyc}-tab001-012.{ext}"
        if fetch(f"{base}.{ext}", p):
            nsf_paths[(cyc, ext)] = p

cip_csv = RAW / "CIPCode2020.csv"
fetch("https://nces.ed.gov/ipeds/cipcode/Files/CIPCode2020.csv", cip_csv)

# ================================================================ 2. BUILD DB
if DB.exists():
    DB.unlink()
con = duckdb.connect(str(DB))

L("# IPEDS graduate outcomes - ingest log")
L()
L(f"Generated by `src/01_ingest.py` on {dt.datetime.now().isoformat(timespec='seconds')}. "
  "Rebuilt from scratch every run; zips in `data_raw/` are reused when present.")
L()

schema_notes = []

# ---------------------------------------------------------------- completions
def pick_member(zpath, prefer_rv=True):
    names = [i.filename for i in members(zpath) if i.filename.lower().endswith(".csv")]
    rv = [n for n in names if n.lower().endswith("_rv.csv")]
    orig = [n for n in names if n not in rv]
    return (rv[0] if rv and prefer_rv else orig[0]), (orig[0] if orig else None), (rv[0] if rv else None)

comp_frames, comp_cols, comp_rows, rv_vs_orig = [], {}, [], []
used_by_zip = {}
KEEP_C = ["UNITID", "CIPCODE", "MAJORNUM", "AWLEVEL", "XCTOTALT", "CTOTALT", "CTOTALM", "CTOTALW"]


def load_completions(y, force_release=None):
    zp = paths[f"C{y}_A"]
    chosen, orig, rv = pick_member(zp)
    df, enc = read_zip_csv(zp, chosen)
    comp_cols[y] = (chosen, list(df.columns))
    out = pd.DataFrame({
        "unitid": num(df["UNITID"]).astype("Int64"),
        "year": y,
        "cipcode": df["CIPCODE"],
        "majornum": num(df["MAJORNUM"]).astype("Int64"),
        "awlevel": num(df["AWLEVEL"]).astype("Int64"),
        "ctotalt": num(df["CTOTALT"]).astype("Int64"),
        "ctotalm": num(df["CTOTALM"]).astype("Int64"),
        "ctotalw": num(df["CTOTALW"]).astype("Int64"),
        "xctotalt": df["XCTOTALT"],
        "source_file": chosen,
    })
    used_by_zip[zp.name] = {chosen: True}
    return out, orig, rv, enc


# final-release completions
for y in YEARS:
    out, orig, rv, enc = load_completions(y)
    out["release"] = "final_revised" if rv else "final_unrevised"
    comp_frames.append(out)
    # compare original vs revised file
    if orig and rv:
        a, _ = read_zip_csv(paths[f"C{y}_A"], orig)
        b, _ = read_zip_csv(paths[f"C{y}_A"], rv)
        def tot(d):
            m = (d["CIPCODE"] == "99") & (num(d["AWLEVEL"]) == 7) & (num(d["MAJORNUM"]) == 1)
            return int(num(d.loc[m, "CTOTALT"]).sum())
        rv_vs_orig.append((y, orig, len(a), a["UNITID"].nunique(), tot(a), rv, len(b), b["UNITID"].nunique(), tot(b)))
        used_by_zip[paths[f"C{y}_A"].name][orig] = False
completions = pd.concat(comp_frames, ignore_index=True)

# 2024: check whether it is provisional or final
c24_final = False
c24_intro = []
if "C2024_A" in paths:
    c24_intro = dict_intro(paths["C2024_A_Dict"]) if "C2024_A_Dict" in paths else []
    c24_members = [i.filename for i in members(paths["C2024_A"])]
    c24_final = any(m.lower().endswith("_rv.csv") for m in c24_members) and not any(
        "provisional" in s.lower() for s in c24_intro[:2])
if c24_final:
    out, _, _, _ = load_completions(2024)
    out["release"] = "final_revised"
    completions = pd.concat([completions, out], ignore_index=True)
con.register("completions_df", completions)
con.execute("CREATE TABLE completions AS SELECT * FROM completions_df")
con.unregister("completions_df")

comp24 = None
if "C2024_A" in paths and not c24_final:
    out, _, _, _ = load_completions(2024)
    out["release"] = "provisional"
    comp24 = out
    con.register("c24", comp24)
    con.execute("CREATE TABLE completions_2024_provisional AS SELECT * FROM c24")
    con.unregister("c24")

# ---------------------------------------------------------------- enrollment
ef_frames, ef_cols, ef_levels = [], {}, {}
ef_dict_rows = dict_codes(paths["EF2023A_Dict"], "Frequencies", {"EFALEVEL", "LINE", "SECTION", "LSTUDY"})
grad_codes = sorted({int(c) for v, c, lab in ef_dict_rows
                     if v == "EFALEVEL" and "graduate" in lab.lower() and "undergraduate" not in lab.lower()})
for y in YEARS:
    zp = paths[f"EF{y}A"]
    chosen, orig, rv = pick_member(zp)
    df, enc = read_zip_csv(zp, chosen)
    ef_cols[y] = (chosen, list(df.columns))
    df["EFALEVEL_I"] = num(df["EFALEVEL"]).astype("Int64")
    ef_levels[y] = df["EFALEVEL_I"].value_counts().sort_index().to_dict()
    g = df[df["EFALEVEL_I"].isin(grad_codes)].copy()
    cnt_cols = [c for c in df.columns if c.startswith("EF") and c not in ("EFALEVEL", "EFALEVEL_I")]
    out = pd.DataFrame({"unitid": num(g["UNITID"]).astype("Int64"), "year": y,
                        "efalevel": g["EFALEVEL_I"], "line": num(g["LINE"]).astype("Int64"),
                        "section": num(g["SECTION"]).astype("Int64"),
                        "lstudy": num(g["LSTUDY"]).astype("Int64")})
    for c in cnt_cols:
        out[c.lower()] = num(g[c]).astype("Int64")
    out["xeftotlt"] = g["XEFTOTLT"]
    out["source_file"] = chosen
    out["release"] = "final_revised" if rv else "as_published"
    used_by_zip[zp.name] = {chosen: True}
    ef_frames.append(out)
enrollment = pd.concat(ef_frames, ignore_index=True)
con.register("enr", enrollment)
con.execute("CREATE TABLE enrollment AS SELECT * FROM enr")
con.unregister("enr")

enr_codes = pd.DataFrame(
    [(v, c, lab, (v == "EFALEVEL" and int(c) in grad_codes)) for v, c, lab in ef_dict_rows],
    columns=["varname", "code", "label", "is_graduate_level_kept"])
con.register("enr_codes_df", enr_codes)
con.execute("CREATE TABLE enrollment_codes AS SELECT * FROM enr_codes_df")
con.unregister("enr_codes_df")

# ---------------------------------------------------------------- institutions
HD_WANT = ["UNITID", "INSTNM", "IALIAS", "CITY", "STABBR", "ZIP", "FIPS", "OBEREG", "SECTOR", "ICLEVEL",
           "CONTROL", "HLOFFER", "UGOFFER", "GROFFER", "DEGGRANT", "HBCU", "HOSPITAL", "MEDICAL", "TRIBAL",
           "LOCALE", "OPENPUBL", "ACT", "CYACTIVE", "POSTSEC", "INSTCAT", "C21BASIC", "C18BASIC", "C15BASIC",
           "CCBASIC", "LANDGRNT", "INSTSIZE", "CBSA", "CBSATYPE", "CSA", "COUNTYCD", "COUNTYNM", "LONGITUD",
           "LATITUDE", "OPEID", "F1SYSNAM"]
INT_COLS = {"UNITID", "FIPS", "OBEREG", "SECTOR", "ICLEVEL", "CONTROL", "HLOFFER", "UGOFFER", "GROFFER", "DEGGRANT",
            "HBCU", "HOSPITAL", "MEDICAL", "TRIBAL", "LOCALE", "OPENPUBL", "CYACTIVE", "POSTSEC", "INSTCAT",
            "C21BASIC", "C18BASIC", "C15BASIC", "CCBASIC", "LANDGRNT", "INSTSIZE", "CBSATYPE"}
FLOAT_COLS = {"LONGITUD", "LATITUDE"}
hd_frames, hd_cols, hd_files, hd_enc = [], {}, {}, {}
for y in YEARS + [2024]:
    if f"HD{y}" not in paths:
        continue
    zp = paths[f"HD{y}"]
    chosen = [i.filename for i in members(zp) if i.filename.lower().endswith(".csv")][0]
    df, enc = read_zip_csv(zp, chosen)
    hd_cols[y] = list(df.columns)
    hd_files[y] = chosen
    hd_enc[y] = enc
    out = pd.DataFrame({"year": y}, index=df.index)
    for c in HD_WANT:
        if c in df.columns:
            if c in INT_COLS:
                out[c.lower()] = num(df[c]).astype("Int64")
            elif c in FLOAT_COLS:
                out[c.lower()] = num(df[c])
            else:
                out[c.lower()] = df[c]
        else:
            out[c.lower()] = pd.NA
    out["source_file"] = chosen
    used_by_zip[zp.name] = {chosen: True}
    hd_frames.append(out)
inst = pd.concat(hd_frames, ignore_index=True)
# Carnegie: one best-available basic classification per row (2021 update preferred, else 2018, else 2015)
inst["carnegie_basic"] = inst["c21basic"].where(inst["c21basic"].notna() & (inst["c21basic"] != -2), inst["c18basic"])
inst["carnegie_basic_vintage"] = pd.Series(
    ["2021" if (pd.notna(a) and a != -2) else ("2018" if (pd.notna(b) and b != -2) else None)
     for a, b in zip(inst["c21basic"], inst["c18basic"])])
inst.loc[inst["carnegie_basic_vintage"].isna(), "carnegie_basic"] = pd.NA
con.register("inst_df", inst)
con.execute("CREATE TABLE institutions AS SELECT * FROM inst_df")
con.unregister("inst_df")

# ---------------------------------------------------------------- awlevel labels
aw_rows = dict_codes(paths["C2023_A_Dict"], "FrequenciesRV", {"AWLEVEL"})
aw24 = dict_codes(paths["C2024_A_Dict"], "Frequencies", {"AWLEVEL"}) if "C2024_A_Dict" in paths else []
AGG = {"12", "13", "14", "15"}
GROUP = {"1": "certificate <1yr", "20": "certificate <1yr", "21": "certificate <1yr", "2": "certificate 1-<2yr",
         "4": "certificate 2-<4yr", "3": "associate", "5": "bachelor", "6": "postbaccalaureate certificate",
         "7": "master", "8": "post-master certificate", "17": "doctorate", "18": "doctorate", "19": "doctorate",
         "12": "aggregate", "13": "aggregate", "14": "aggregate", "15": "aggregate"}
awl = pd.DataFrame([(int(c), lab.strip(), GROUP.get(c, "other"), c in AGG,
                     c in {"6", "7", "8", "17", "18", "19"}) for _, c, lab in aw_rows],
                   columns=["awlevel", "label", "level_group", "is_aggregate_total", "is_graduate_level"]
                   ).sort_values("awlevel")
con.register("awl_df", awl)
con.execute("CREATE TABLE awlevel_labels AS SELECT * FROM awl_df")
con.unregister("awl_df")

# ---------------------------------------------------------------- CIP titles
def unwrap(v):
    m = re.fullmatch(r'="(.*)"', v)
    return m.group(1) if m else v

raw = cip_csv.read_bytes()
try:
    txt = raw.decode("utf-8-sig")
except UnicodeDecodeError:
    txt = raw.decode("cp1252")
cip_rows = list(csv.DictReader(io.StringIO(txt)))
cip = []
for r in cip_rows:
    code = unwrap(r["CIPCode"]).strip()
    fam = unwrap(r["CIPFamily"]).strip()
    level = {2: "family", 5: "series"}.get(len(code), "program" if len(code) == 7 else "other")
    cip.append((code, level, fam, r["CIPTitle"].strip().rstrip("."), r["CIPDefinition"].strip()))
cipdf = pd.DataFrame(cip, columns=["cipcode", "cip_level", "family2", "title", "definition"])
cipdf["title_ipeds_dictionary"] = None
cipdf["source"] = "NCES CIPCode2020.csv"
# IPEDS dictionary titles (FrequenciesRV of C2023 and Frequencies of C2024) for 6-digit program codes + '99'
dict_titles = {}
for zname, sheet in (("C2023_A_Dict", "FrequenciesRV"), ("C2024_A_Dict", "Frequencies")):
    if zname in paths:
        for _, c, lab in dict_codes(paths[zname], sheet, {"CIPCODE"}):
            dict_titles[c] = lab.strip()
cipdf["title_ipeds_dictionary"] = cipdf["cipcode"].map(dict_titles)
extra = [(c, "total" if c == "99" else "program", c[:2], None, None, t, "IPEDS dictionary only")
         for c, t in dict_titles.items() if c not in set(cipdf["cipcode"])]
if extra:
    cipdf = pd.concat([cipdf, pd.DataFrame(extra, columns=["cipcode", "cip_level", "family2", "title",
                                                          "definition", "title_ipeds_dictionary", "source"])],
                      ignore_index=True)
cipdf.loc[cipdf["cipcode"] == "99", "title"] = "Grand total"
con.register("cip_df", cipdf)
con.execute("CREATE TABLE cip_titles AS SELECT * FROM cip_df")
con.unregister("cip_df")

# ---------------------------------------------------------------- NSF SED table 1-12
nsf_rows, nsf_meta = [], []
newest = NSF_CYCLES[0][0]
avail_cycles = [c for c, _ in NSF_CYCLES if (c, "xlsx") in nsf_paths]
newest = avail_cycles[0] if avail_cycles else None
SECTORS = {"All fields": "total", "Science and engineering": "sector", "Non-science and engineering": "sector"}
for cyc, base in NSF_CYCLES:
    if (cyc, "xlsx") not in nsf_paths:
        continue
    wb = openpyxl.load_workbook(nsf_paths[(cyc, "xlsx")], data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
    title_no, title, unit = [plain(rows[i][0]) for i in range(3)]
    hdr = rows[3]
    years = [int(v) for v in hdr[1:] if v is not None]
    field, parent_sector, ftype = None, None, None
    n_data = 0
    for r in rows[4:]:
        label = str(r[0]).strip()
        if r[1] is None or str(r[1]).strip() == "":
            field = label
            if label in SECTORS:
                ftype = SECTORS[label]
                parent_sector = label if ftype == "sector" else None
            else:
                ftype = "broad_field"
            continue
        foot = None
        m = re.fullmatch(r"(Since starting doctoral program)([a-z])", label)
        if m:
            label, foot = m.group(1), m.group(2)
        for yv, v in zip(years, r[1:]):
            vt = str(v).strip()
            val = float(v) if isinstance(v, (int, float)) else None
            nsf_rows.append((cyc, field, ftype, parent_sector if ftype == "broad_field" else (field if ftype == "sector" else None),
                             label, yv, val, vt, foot, newest == cyc))
            n_data += 1
    note_txt = ""
    if (cyc, "pdf") in nsf_paths:
        try:
            import pypdf
            t = "\n".join(p.extract_text() for p in pypdf.PdfReader(nsf_paths[(cyc, "pdf")]).pages)
            i = t.find("na = not applicable")
            note_txt = plain(re.sub(r"\s+", " ", t[i:])) if i >= 0 else ""
        except Exception as e:  # pypdf missing etc.
            note_txt = f"(PDF note extraction failed: {e!r}; see PDF in data_raw)"
    nsf_meta.append((cyc, base + ".xlsx", title_no, title, unit, f"{years[0]}-{years[-1]}", note_txt,
                     stamp(nsf_paths[(cyc, "xlsx")]), newest == cyc))
nsf = pd.DataFrame(nsf_rows, columns=["cycle", "field", "field_type", "parent_sector", "measure", "year",
                                       "value", "value_raw", "footnote_marker", "is_newest_cycle"])
nsf["table_title"] = nsf["cycle"].map({m[0]: m[3] for m in nsf_meta})
nsf["source_url"] = nsf["cycle"].map({m[0]: m[1] for m in nsf_meta})
con.register("nsf_df", nsf)
con.execute("CREATE TABLE nsf_sed_median_years AS SELECT * FROM nsf_df")
con.unregister("nsf_df")
nsfm = pd.DataFrame(nsf_meta, columns=["cycle", "source_url", "table_number", "table_title", "unit",
                                        "year_range", "note_text", "downloaded_at", "is_newest_cycle"])
con.register("nsfm_df", nsfm)
con.execute("CREATE TABLE nsf_sed_table_meta AS SELECT * FROM nsfm_df")
con.unregister("nsfm_df")

# ---------------------------------------------------------------- manifest
for k, p in paths.items():
    note = ""
    if k == "C2024_A":
        note = "provisional release (not in completions table)" if not c24_final else ""
    note_manifest(p, IPEDS.format(k), used_by_zip.get(p.name, {}), note)
for (cyc, ext), p in nsf_paths.items():
    manifest.append(dict(file=p.name, zip_file=None, url=f"{dict(NSF_CYCLES)[cyc]}.{ext}", rows=None,
                         bytes=p.stat().st_size, member_bytes=p.stat().st_size, sha256=sha256(p),
                         downloaded_at=stamp(p), status="ok", loaded=(ext == "xlsx"), note="NSF SED Table 1-12"))
manifest.append(dict(file=cip_csv.name, zip_file=None, url="https://nces.ed.gov/ipeds/cipcode/Files/CIPCode2020.csv",
                     rows=len(cip_rows), bytes=cip_csv.stat().st_size, member_bytes=cip_csv.stat().st_size,
                     sha256=sha256(cip_csv), downloaded_at=stamp(cip_csv), status="ok", loaded=True,
                     note="CIP 2020 titles"))
for name, url, why in unavailable:
    manifest.append(dict(file=name, zip_file=None, url=url, rows=None, bytes=0, member_bytes=0, sha256=None,
                         downloaded_at=dt.datetime.now().isoformat(timespec="seconds"), status="unavailable",
                         loaded=False, note=why))
mf = pd.DataFrame(manifest)
con.register("mf", mf)
con.execute("CREATE TABLE ingest_manifest AS SELECT * FROM mf")
con.unregister("mf")

# ================================================================ 3. LOG
q = lambda s: con.execute(s).fetchall()
L("## Tables in data/ipeds.duckdb")
L()
L("| table | rows | note |")
L("|---|---|---|")
notes = {
    "completions": "C{yr}_A, final/revised (_RV) file; year = IPEDS file year (2023 = academic year 2022-23)",
    "completions_2024_provisional": "C2024_A is PROVISIONAL (Sept 2025); kept separate, NOT in completions",
    "enrollment": "EF{yr}A fall enrollment, graduate EFALEVEL codes only (12, 32, 52)",
    "enrollment_codes": "EF2023A_Dict code labels (EFALEVEL, LINE, SECTION, LSTUDY)",
    "institutions": "HD{yr}, one row per institution per year (2020-2024)",
    "cip_titles": "CIP 2020 titles (NCES CIPCode2020.csv) + IPEDS dictionary titles",
    "awlevel_labels": "AWLEVEL code labels from C2023_A_Dict (FrequenciesRV)",
    "nsf_sed_median_years": "NSF SED Table 1-12 (two cycles), tidy long",
    "nsf_sed_table_meta": "titles, source URLs, note text per NSF cycle",
    "ingest_manifest": "one row per source csv/file",
}
for (t,) in q("SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1"):
    L(f"| {t} | {q(f'SELECT count(*) FROM {t}')[0][0]:,} | {notes.get(t, '')} |")
L()

L("## Source files and release status")
L()
L("| zip | csv member | rows | loaded | note |")
L("|---|---|---|---|---|")
for m in manifest:
    if m["status"] == "ok" and m["file"].lower().endswith(".csv") and m["zip_file"]:
        L(f"| {m['zip_file']} | {m['file']} | {m['rows']:,} | {'yes' if m['loaded'] else 'no'} | {m['note']} |")
L()
L("Unavailable / probed-but-missing files:")
L()
for name, url, why in unavailable:
    L(f"- {name}: {why} ({url})")
if not unavailable:
    L("- none")
L()
L("Release decisions:")
L()
L("- Completions 2020-2023: every zip contains both the original (provisional) csv and a `_rv` (final/revised) csv; "
  "the `_rv` file is loaded. C2023_A.zip `C2023_a_RV.csv` carries a final/revised release dated September 2025.")
L("- C2024_A has no `_RV` file and its dictionary says '(Provisional release)', September 2025. It is therefore "
  "NOT final and is stored only in `completions_2024_provisional`.")
L("- EF2024A.zip does not exist on the NCES data center (HTTP 404), so enrollment stops at fall 2023 (EF2023A, no _RV file). "
  "EF2020A-EF2022A load the `_rv` csv.")
L("- Intro lines from dictionaries:")
for z in ("C2023_A_Dict", "C2024_A_Dict", "EF2023A_Dict"):
    if z in paths:
        L(f"  - {z}: " + " / ".join(dict_intro(paths[z])[:3]))
L()
L("### Revised vs original completions file (master's degrees AWLEVEL 7, CIPCODE 99, MAJORNUM 1 total)")
L()
L("| year | original file | rows | institutions | masters total | revised file | rows | institutions | masters total |")
L("|---|---|---|---|---|---|---|---|---|")
for r in rv_vs_orig:
    L("| " + " | ".join(f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) and v > 3000 else str(v) for v in r) + " |")
L()

L("## Row counts per year")
L()
L("| year | completions rows | completions institutions | enrollment (grad) rows | enrollment institutions | HD rows |")
L("|---|---|---|---|---|---|")
for y in YEARS + [2024]:
    c = q(f"SELECT count(*), count(DISTINCT unitid) FROM completions WHERE year={y}")[0]
    if y == 2024 and comp24 is not None:
        c = q("SELECT count(*), count(DISTINCT unitid) FROM completions_2024_provisional")[0]
        cs = f"{c[0]:,} (provisional table)"
    else:
        cs = f"{c[0]:,}"
    e = q(f"SELECT count(*), count(DISTINCT unitid) FROM enrollment WHERE year={y}")[0]
    h = q(f"SELECT count(*) FROM institutions WHERE year={y}")[0][0]
    L(f"| {y} | {cs} | {c[1]:,} | {e[0]:,} | {e[1]:,} | {h:,} |")
L()

L("## Sanity checks")
L()
r23 = [m for m in rv_vs_orig if m[0] == 2023]
cnt23 = q("SELECT count(*), count(DISTINCT unitid) FROM completions WHERE year=2023")[0]
L(f"- FY2023 completions: original (provisional) file has {r23[0][2]:,} rows / {r23[0][3]:,} institutions "
  f"(these are the counts of the ORIGINAL file). The final/revised file loaded into `completions` has "
  f"{cnt23[0]:,} rows / {cnt23[1]:,} institutions." if r23 else "- FY2023 comparison unavailable")
dups = q("SELECT count(*) FROM (SELECT unitid, year, cipcode, majornum, awlevel, count(*) n FROM completions GROUP BY ALL HAVING n>1)")[0][0]
L(f"- Duplicate (unitid, year, cipcode, majornum, awlevel) keys in completions: {dups}")
nulls = q("SELECT count(*) FILTER (WHERE ctotalt IS NULL), count(*) FILTER (WHERE ctotalm IS NULL) FROM completions")[0]
L(f"- completions NULL ctotalt / ctotalm after numeric parse: {nulls[0]} / {nulls[1]}")
missing_cip = q("""SELECT count(DISTINCT c.cipcode) FROM completions c LEFT JOIN cip_titles t USING (cipcode) WHERE t.cipcode IS NULL""")[0][0]
L(f"- Distinct completions CIPCODE values with no row in cip_titles: {missing_cip}")
if missing_cip:
    L("  - examples: " + ", ".join(r[0] for r in q("""SELECT DISTINCT c.cipcode FROM completions c LEFT JOIN cip_titles t USING (cipcode) WHERE t.cipcode IS NULL ORDER BY 1 LIMIT 15""")))
inst_miss = q("""SELECT count(DISTINCT c.unitid) FROM completions c LEFT JOIN institutions i ON c.unitid=i.unitid AND c.year=i.year WHERE i.unitid IS NULL""")[0][0]
L(f"- Completions institutions (any year) with no HD row for the same year: {inst_miss}")
L(f"- Institutions per HD year: " + ", ".join(f"{y}: {n:,}" for y, n in q("SELECT year, count(*) FROM institutions GROUP BY 1 ORDER BY 1")))
L()

L("## Distinct codes")
L()
L("AWLEVEL in completions (all loaded years) with label:")
L()
L("| awlevel | label | group | aggregate total? | rows |")
L("|---|---|---|---|---|")
for a, lab, g, agg, n in q("""SELECT a.awlevel, a.label, a.level_group, a.is_aggregate_total, count(c.unitid)
                             FROM awlevel_labels a LEFT JOIN completions c USING (awlevel) GROUP BY ALL ORDER BY 1"""):
    L(f"| {a} | {lab} | {g} | {'YES' if agg else ''} | {n:,} |")
unlabeled = q("SELECT DISTINCT awlevel FROM completions WHERE awlevel NOT IN (SELECT awlevel FROM awlevel_labels)")
L()
L(f"AWLEVEL codes in data without a label: {[u[0] for u in unlabeled] or 'none'}. "
  f"C2024 dictionary AWLEVEL codes identical to C2023: {sorted(c for _, c, _ in aw24) == sorted(c for _, c, _ in aw_rows) if aw24 else 'n/a'}.")
L()
L("Notes: AWLEVEL 12, 13, 14, 15 are rollup-total codes in the dictionary but have ZERO rows in the data files; "
  "AWLEVEL 1 (certificates <1 yr) also has zero rows since 2019-20 (replaced by 20 and 21). "
  "CIPCODE '99' IS a grand-total row (one per institution x award level x major number) and MAJORNUM 1 and 2 both exist, "
  "so summing all rows double counts. For degree counts use awlevel=7 (or 17/18/19), majornum=1 and cipcode<>'99' (or only cipcode='99').")
L()
L("EFALEVEL present in the raw EF files (all rows) per year, count of institution-rows:")
L()
allcodes = sorted({k for y in ef_levels for k in ef_levels[y]})
L("| EFALEVEL | " + " | ".join(str(y) for y in YEARS) + " | label | kept |")
L("|---|" + "---|" * (len(YEARS) + 2))
lab = {int(c): l for v, c, l in ef_dict_rows if v == "EFALEVEL"}
for code in allcodes:
    L(f"| {code} | " + " | ".join(f"{ef_levels[y].get(code, 0):,}" for y in YEARS) + f" | {lab.get(code, '?')} | {'yes' if code in grad_codes else ''} |")
L()
L(f"Graduate EFALEVEL codes kept (label contains 'Graduate' but not 'Undergraduate'): {grad_codes}  "
  "(12 = All students, Graduate; 32 = Full-time students, Graduate; 52 = Part-time students, Graduate).")
L()
ef_line = q("SELECT efalevel, line, section, lstudy, count(*) FROM enrollment GROUP BY ALL ORDER BY 1")
L("Kept enrollment rows by (efalevel, line, section, lstudy): " + "; ".join(str(tuple(r)) for r in ef_line))
L("LINE 99 = 'Generated record not on original survey' (derived row, e.g. EFALEVEL 12). "
  "LSTUDY: 1 undergraduate, 3 graduate, 4 all students.")
L()

L("## Schema differences across years")
L()
base_c = set(comp_cols[2023][1])
L("Completions (all years): " + ("identical 64-column layout 2020-2023" if all(set(v[1]) == base_c for v in comp_cols.values()) else
  "column differences: " + "; ".join(f"{y}: +{sorted(set(v[1])-base_c)} -{sorted(base_c-set(v[1]))}" for y, v in comp_cols.items() if set(v[1]) != base_c)) +
  ". Column names are padded/uppercase in some files (last header e.g. `CNRALW  ` has trailing spaces) so names are stripped and upper-cased. "
  "No `YEAR` column exists in the source: `year` is added from the file name. `AWLEVEL` codes 20 and 21 (certificates <12 weeks / 12 weeks-<1 year) exist since 2019-20 alongside 1.")
L()
L("Completions file members loaded: " + "; ".join(f"{y}: {v[0]}" for y, v in comp_cols.items()))
L()
base_e = set(ef_cols[2023][1])
for y in YEARS:
    d_plus = sorted(set(ef_cols[y][1]) - base_e)
    d_minus = sorted(base_e - set(ef_cols[y][1]))
    L(f"- EF{y}A ({ef_cols[y][0]}, {len(ef_cols[y][1])} cols): missing vs 2023: {d_minus or 'none'}; extra: {d_plus or 'none'}")
L("- The gender-unknown/another-gender count columns (EFGNDRUN, EFGNDRAN, EFGNDRUA, EFGNDRKN) first appear in EF2022A; they are NULL for 2020-2021. "
  "EF2022A has misspelled/duplicate imputation-flag headers (XEFGNDRU twice, XEFGNDRA, XEFGNDRK); only count columns (not flags) are kept, plus XEFTOTLT.")
L("- EFALEVEL values in the raw files are space padded (' 1'); values are stripped and cast to integer.")
L()
base_h = set(hd_cols[2023])
for y in sorted(hd_cols):
    L(f"- HD{y} ({hd_files[y]}, decoded as {hd_enc[y]}, {len(hd_cols[y])} cols): missing vs 2023: {sorted(base_h - set(hd_cols[y])) or 'none'}; extra: {sorted(set(hd_cols[y]) - base_h) or 'none'}")
L("- Carnegie: HD2020 has only C18BASIC/C15BASIC/CCBASIC; HD2021-HD2023 add C21BASIC; HD2024 renames the Carnegie block "
  "(C00CARNEGIE, C21BASIC, CARNEGIEIC, CARNEGIESAEC, CARNEGIERSCH, ...) and drops C18BASIC/C15BASIC/CCBASIC. "
  "`institutions.carnegie_basic` takes C21BASIC when populated (not -2 'not applicable') else C18BASIC; `carnegie_basic_vintage` records which. "
  "Code meanings are not loaded (no dictionary table for HD); see HD2023_Dict in data_raw.")
L("- HD files 2023-2024 start with a UTF-8 BOM in the first header (stripped). Some HD csv files are cp1252 not UTF-8 (decoded with fallback).")
L()

L("## CIP titles")
L()
lv = q("SELECT cip_level, count(*) FROM cip_titles GROUP BY 1 ORDER BY 1")
L("cip_titles rows by level: " + ", ".join(f"{a}: {b:,}" for a, b in lv) +
  ". 2-digit family titles, 4-digit series titles and 6-digit program titles all come from NCES `CIPCode2020.csv` "
  "(IPEDS completions 2020-2024 all use CIP 2020). The IPEDS dictionary's own 6-digit titles are stored in `title_ipeds_dictionary` "
  "(the dictionary has no 2-digit family titles). CIP titles in the NCES file are upper case for the family level and end with a period (stripped).")
L()

L("## NSF SED Table 1-12")
L()
for m in nsf_meta:
    L(f"- cycle {m[0]} ({'NEWEST' if m[8] else 'older'}): {m[2]} - {m[3]}; years {m[5]}; source {m[1]}")
    L(f"  - note text: {m[6] or '(none extracted)'}")
nn = q("SELECT cycle, count(*), count(DISTINCT field), count(DISTINCT measure), min(year), max(year) FROM nsf_sed_median_years GROUP BY 1 ORDER BY 1 DESC")
for r in nn:
    L(f"- {r[0]}: {r[1]} tidy rows, {r[2]} fields, {r[3]} measures, years {r[4]}-{r[5]}")
L("- Measures present: " + ", ".join(r[0] for r in q("SELECT DISTINCT measure FROM nsf_sed_median_years ORDER BY 1")) +
  ". There is NO 'registered time' row in Table 1-12 (the xlsx has three time bases only).")
L("- The two cycles use different year grids (nsf25349: 1974, 1979, ... 2024; nsf26326: 1975, 1980, ... 2025), so both are kept with a `cycle` column; "
  "`is_newest_cycle` flags nsf26326. The two grids share no calendar year, so values cannot be compared year by year across cycles.")
chk = q("""SELECT cycle, measure, year, value FROM nsf_sed_median_years WHERE field='All fields'
           AND measure IN ('Since starting graduate school','Since starting doctoral program') AND year IN (2024, 2025) ORDER BY 1,2,3""")
L("- Verification, All fields: " + "; ".join(f"{c} {m} {y} = {v}" for c, m, y, v in chk) +
  ". The expected 7.3 / 5.7 for 2024 is in nsf25349 (SED 2024 cycle); the newest cycle nsf26326 reports 2025 = 7.0 / 5.8.")
L("- Non-numeric cells kept as `value_raw` with `value` NULL: " + ", ".join(f"{r[0]!r} x{r[1]}" for r in q("SELECT value_raw, count(*) FROM nsf_sed_median_years WHERE value IS NULL GROUP BY 1")) +
  " ('na' = not applicable, data not collected at that level of detail; '-' in nsf25349 for Computer sciences 1974).")
L()

L("## Problems and caveats")
L()
L("- C2024_A is provisional only; EF2024A is not published (404). Latest year with data for all three surveys is 2023 "
  "(completions final/revised, enrollment provisional). HD2024 exists and is loaded.")
L("- Completions CIPCODE values are only 6-digit codes (dd.dddd) plus '99' (grand total); no 2-digit or 4-digit rollup rows exist in the data, "
  "so family-level figures must be aggregated by the first 2 characters of cipcode.")
L("- AWLEVEL and MAJORNUM are zero padded in the 2020 file (e.g. '05', '07'); they are cast to integers on load. "
  "The master's-total comparison above uses the numeric cast (a string comparison would give 0 for padded years).")
L("- EF2023A (fall 2023) is labelled 'Provisional release' in its dictionary and no _RV file exists, so the enrollment table's latest year is provisional.")
L("- No hand edits to raw downloads; all parsing is in this script.")
L()
L("Manifest columns: file, zip_file, url, rows, bytes (zip size), member_bytes (uncompressed), sha256 (of the zip), downloaded_at (file mtime), status, loaded, note.")

LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
con.close()
print("done:", DB)
for t in (r for r in log_lines[:20]):
    pass
