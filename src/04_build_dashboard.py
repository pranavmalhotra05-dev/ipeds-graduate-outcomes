"""Build dashboard/graduate_outcomes_dashboard.html (single self-contained file).

Reads ONLY tableau_ready/*.csv (suppressed at 10). Embeds plotly.js inline.
Also copies the page to docs/index.html for GitHub Pages.
Template: dashboard/template.html. Run: python src/04_build_dashboard.py
"""
import json, math, os, sys
import pandas as pd
import plotly

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TR = os.path.join(ROOT, 'tableau_ready')
DASH = os.path.join(ROOT, 'dashboard')
OUT = os.path.join(DASH, 'graduate_outcomes_dashboard.html')
YEARS = [2020, 2021, 2022, 2023]
LEVELS = ['masters', 'research_doctorate', 'professional_doctorate', 'other_doctorate', 'all_masters_doctoral']
LEVEL_LABELS = {
    'masters': "Master's degree",
    'research_doctorate': "Doctor's - research/scholarship",
    'professional_doctorate': "Doctor's - professional practice",
    'other_doctorate': "Doctor's - other",
    'all_masters_doctoral': "All master's and doctoral levels",
}


def clean(v, nd=None):
    if isinstance(v, str):
        return v
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    f = float(v)
    if nd is None and f.is_integer():
        return int(f)
    return round(f, nd) if nd is not None else f


def rows(df, cols, nds=None):
    nds = nds or {}
    return [[clean(v, nds.get(c)) for c, v in zip(cols, rec)]
            for rec in df[cols].itertuples(index=False, name=None)]


def rd(name, **kw):
    return pd.read_csv(os.path.join(TR, name), **kw)


def main():
    dim = rd('institution_dim.csv', dtype={'unitid': int})
    prog = rd('program_completions_by_year.csv', dtype={'cipcode': str, 'cip2': str})
    isum = rd('institution_summary.csv')
    fsum = rd('field_summary.csv', dtype={'cip2': str})
    sup = rd('suppression_impact.csv')
    sed = rd('sed_benchmark.csv')
    nat = rd('national_totals.csv')

    # ---- program cells grouped per institution; -1 = suppressed, null = no record
    assert (prog.loc[prog.suppressed == 0, 'display_count'] >= 10).all(), 'unsuppressed count below 10'
    assert prog.loc[prog.suppressed == 1, 'display_count'].isna().all(), 'suppressed row has a count'
    cip = prog[['cipcode', 'cip_title', 'cip2']].drop_duplicates('cipcode').sort_values('cipcode')
    cip_idx = {c: i for i, c in enumerate(cip.cipcode)}
    cip2 = prog[['cip2', 'cip2_title']].drop_duplicates('cip2').sort_values('cip2')
    lvl_code = {7: 'masters', 17: 'research_doctorate', 18: 'professional_doctorate', 19: 'other_doctorate'}
    lvl_idx = {k: i for i, k in enumerate(LEVELS)}
    prog = prog.assign(val=prog.display_count.where(prog.suppressed == 0, -1),
                       lv=prog.award_level_code.map(lambda c: lvl_idx[lvl_code[c]]),
                       ci=prog.cipcode.map(cip_idx))
    progd = {}
    for (u, ci, lv), g in prog.groupby(['unitid', 'ci', 'lv'], sort=False):
        arr = [None] * 4
        for y, v in zip(g.year, g.val):
            arr[YEARS.index(int(y))] = int(v)
        progd.setdefault(str(int(u)), []).append([int(ci), int(lv)] + arr)

    # ---- institution summary rows
    lk = {k: i for i, k in enumerate(LEVELS)}
    isum = isum.assign(lv=isum.level_key.map(lk), cs=isum.completions_suppressed.astype(int))
    icols = ['unitid', 'lv', 'year', 'completions_total', 'cs', 'n_program_cells', 'n_program_cells_suppressed',
             'grad_enrollment_total', 'ratio_completions_to_grad_enrollment',
             'ratio_completions_to_prior_fall_grad_enrollment', 'completions_prior_year',
             'n_program_cells_prior_year', 'yoy_pct_change', 'completions_2020', 'n_program_cells_2020',
             'pct_change_vs_2020']
    nds = {'ratio_completions_to_grad_enrollment': 4, 'ratio_completions_to_prior_fall_grad_enrollment': 4,
           'yoy_pct_change': 2, 'pct_change_vs_2020': 2}
    isum_rows = rows(isum, icols, nds)

    a23 = isum[(isum.year == 2023) & (isum.level_key == 'all_masters_doctoral')].dropna(subset=['completions_total'])
    default_unit = int(a23.sort_values('completions_total').iloc[-1].unitid)

    inst = [[int(r.unitid), r.instnm, r.stabbr, r.control_label,
             (r.carnegie_label if isinstance(r.carnegie_label, str) else 'Not classified'),
             int(bool(r.has_graduate_enrollment)), int(r.n_years_with_completions)]
            for r in dim.sort_values('instnm').itertuples()]

    fcols = ['year', 'cip2', 'cip2_title', 'level_key', 'completions_total', 'completions_suppressed',
             'n_institutions', 'n_program_cells', 'n_program_cells_lt10', 'share_program_cells_lt10',
             'share_completions_in_cells_lt10', 'n_program_cells_suppressed_incl_complementary',
             'yoy_pct_change', 'n_program_cells_prior_year', 'n_institutions_prior_year',
             'sed_broad_field_approx']
    fnds = {'share_program_cells_lt10': 4, 'share_completions_in_cells_lt10': 4, 'yoy_pct_change': 2}
    fsum_rows = rows(fsum, fcols, fnds)

    scols = ['threshold', 'year', 'level_key', 'n_cells', 'n_cells_primary_suppressed', 'share_cells_primary_suppressed',
             'n_cells_suppressed_total', 'share_cells_suppressed_total', 'completions_total_all_cells',
             'completions_in_suppressed_total', 'share_completions_in_suppressed_total', 'n_institutions',
             'n_institutions_all_cells_suppressed_total', 'share_institutions_all_cells_suppressed_total']
    snds = {c: 4 for c in scols if c.startswith('share')}
    sup_rows = rows(sup, scols, snds)

    sed_cols = ['table_id', 'cycle', 'sed_year', 'field', 'field_type', 'measure', 'median_years', 'value_raw',
                'footnote_marker', 'source_url']
    sed_rows = rows(sed, sed_cols)
    ncols = ['year', 'level_key', 'completions_total', 'n_program_cells', 'n_institutions', 'grad_enrollment_total',
             'matched_completions', 'matched_enrollment', 'n_matched_institutions',
             'ratio_completions_to_grad_enrollment_matched',
             'ratio_completions_to_prior_fall_grad_enrollment_matched', 'n_matched_institutions_prior_fall',
             'yoy_pct_change', 'n_institutions_prior_year', 'n_program_cells_prior_year']
    nat_rows = rows(nat, ncols, {'ratio_completions_to_grad_enrollment_matched': 4,
                                 'ratio_completions_to_prior_fall_grad_enrollment_matched': 4, 'yoy_pct_change': 2})

    data = {
        'years': YEARS, 'levels': LEVELS, 'levelLabels': LEVEL_LABELS, 'defaultUnit': default_unit,
        'instCols': ['unitid', 'name', 'state', 'control', 'carnegie', 'hasEnr', 'nYears'], 'inst': inst,
        'cip': [[r.cipcode, r.cip_title, r.cip2] for r in cip.itertuples()],
        'cip2': [[r.cip2, r.cip2_title] for r in cip2.itertuples()],
        'progNote': 'row = [cipIdx, levelIdx, c2020, c2021, c2022, c2023]; -1 = suppressed; null = no record',
        'prog': progd,
        'isumCols': icols, 'isum': isum_rows,
        'fsumCols': fcols, 'fsum': fsum_rows,
        'supCols': scols, 'sup': sup_rows,
        'sedCols': sed_cols, 'sed': sed_rows,
        'natCols': ncols, 'nat': nat_rows,
    }
    js = json.dumps(data, separators=(',', ':'), allow_nan=False, ensure_ascii=True)
    js = js.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')

    pj = os.path.join(os.path.dirname(plotly.__file__), 'package_data', 'plotly.min.js')
    plotly_js = open(pj, encoding='utf-8').read().replace('</script', '<\\/script')
    tpl = open(os.path.join(DASH, 'template.html'), encoding='utf-8').read()
    html = (tpl.replace('/*__PLOTLY__*/', lambda_free(plotly_js), 1)
               .replace('__DATA_JSON__', lambda_free(js), 1)
               .replace('__BUILD_DATE__', pd.Timestamp.now().strftime('%Y-%m-%d')))
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)
    # copy for GitHub Pages (serves docs/index.html)
    docs_dir = os.path.join(ROOT, 'docs')
    os.makedirs(docs_dir, exist_ok=True)
    pages = os.path.join(docs_dir, 'index.html')
    with open(pages, 'w', encoding='utf-8', newline='\n') as f:
        f.write(html)
    print('wrote', os.path.relpath(pages, ROOT))
    print('wrote', os.path.relpath(OUT, ROOT), round(os.path.getsize(OUT) / 1e6, 2), 'MB; data json', round(len(js) / 1e6, 2), 'MB;',
          'prog institutions', len(progd))


def lambda_free(s):
    return s


if __name__ == '__main__':
    sys.exit(main())
