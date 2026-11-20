# Dashboard build notes

Build: `python src/04_build_dashboard.py` (reads only `tableau_ready/*.csv`; template `dashboard/template.html`; plotly.js taken from the installed plotly package and embedded inline). Output: `dashboard/graduate_outcomes_dashboard.html` (about 8.2 MB, works offline), and the same file is copied to `docs/index.html` so GitHub Pages can serve it.

No Tableau workbook is built. This is a static HTML dashboard; the CSVs in `tableau_ready/` are the inputs it embeds.

## Views (tabs; filtered views of one source, not access control, anyone who opens the file sees every view)
- Program director: institution + level + CIP family; family totals by year (displayed cells only, hidden-cell counts in axis labels), single-program chart, full program matrix with "<10" for hidden cells.
- Dean: field mix (displayed cells), yoy and vs-2020 change with program-cell n, ratio over time.
- Graduate dean: ratio vs peers (control / Carnegie / state / national), ratio over time vs peer median, suppression share of own programs vs peers.
- Provost: totals by level 2020-2023, suppression at thresholds 5/10/20, national ratio, top fields, SED Table 1-12 (nsf26326 and nsf25349) labelled as a separate field-level source.

## Data embedded
Program cells grouped per institution (-1 = suppressed, null = no record); all non-suppressed counts are 10 or more. Institution summary, field summary, suppression impact, national totals, SED benchmark. Program data is the 4 years in the CSV (2020-2023).

## Design choices
- Palette is luminance-distinct (navy, burnt orange, mid blue, light gray) with bar patterns (solid, diagonal, cross, dots), marker shapes and dash styles, plus direct labels.
- Each chart has role="img" with a generated aria-label, a visible caption, and a collapsible data table. Tabs support arrow/Home/End keys. Institution search is an HTML datalist.
- Small-n warning thresholds: under 5 program cells, under 30 completions, peer group under 10 institutions.

## Limits
- Field mix and family totals sum displayed cells only and understate true totals; hidden cells are counted, never estimated.
- Ratio exists only at institution/national level and for all levels combined (enrollment has no level or CIP detail).
- SED has no respondent n in the extracted table; no n can be shown for it.
- Plotly charts are not fully keyboard-navigable internally; the data tables are the accessible equivalent.
