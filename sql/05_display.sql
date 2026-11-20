-- 05_display.sql : display (publishable) tables. Suppression threshold = 10 (primary), plus complementary suppression.
-- pct columns are percent units (4.2 = 4.2 percent); ratios are plain ratios (0.45).

-- 1. program-level display table: counts nulled when suppressed
create or replace table m_program_display as
select c.year, c.unitid, c.instnm, c.stabbr, c.control_label,
  c.cipcode, c.cip_title, c.cip2, c.cip2_title,
  c.awlevel as award_level_code, c.level_key, c.level_label as award_level,
  s.suppressed::int as suppressed,
  case when s.prim then 'primary_lt10' when s.comp1 then 'complementary_family'
       when s.comp2 then 'complementary_institution' else 'none' end as suppression_reason,
  case when s.suppressed then null else c.completions end as display_count,
  10 as suppression_threshold
from m_program_cells c
join m_cell_supp s on s.thr = 10 and s.unitid = c.unitid and s.year = c.year
                  and s.cipcode = c.cipcode and s.awlevel = c.awlevel;

-- 2. institution summary display
create or replace table m_inst_summary_display as
with cellsupp as (
  select unitid, year, coalesce(level_key, 'all_masters_doctoral') as level_key,
    sum(suppressed::int) as n_cells_suppressed
  from m_supp_cells_lvl where thr = 10
  group by grouping sets ((unitid, year, level_key), (unitid, year))
), a as (
  select i.*,
    (i.completions < 10)
    or (i.level_key = 'all_masters_doctoral'
        and (sum((i.completions < 10)::int) filter (where i.level_key <> 'all_masters_doctoral')
             over (partition by i.unitid, i.year)) = 1) as sup
  from m_inst_summary_internal i
)
select a.year, a.unitid, d.instnm, d.stabbr, d.control_label,
  a.level_key,
  case a.level_key when 'all_masters_doctoral' then 'All master''s and doctoral levels (7, 17, 18, 19)'
       else l.level_label end as award_level,
  case when a.sup then null else a.completions end as completions_total,
  a.sup::int as completions_suppressed,
  a.n_cells as n_program_cells,
  coalesce(cs.n_cells_suppressed, 0) as n_program_cells_suppressed,
  case when a.level_key = 'all_masters_doctoral' then a.grad_enrollment_total end as grad_enrollment_total,
  case when a.level_key = 'all_masters_doctoral' then a.grad_enrollment_ft end as grad_enrollment_ft,
  case when a.level_key = 'all_masters_doctoral' then a.grad_enrollment_pt end as grad_enrollment_pt,
  case when a.level_key = 'all_masters_doctoral' and not a.sup and a.grad_enrollment_total > 0
       then a.completions * 1.0 / a.grad_enrollment_total end as ratio_completions_to_grad_enrollment,
  case when a.level_key = 'all_masters_doctoral' and not a.sup and a.grad_enrollment_total_prior_fall > 0
       then a.completions * 1.0 / a.grad_enrollment_total_prior_fall end as ratio_completions_to_prior_fall_grad_enrollment,
  case when not pa.sup then pa.completions end as completions_prior_year,
  a.n_cells_prior_year as n_program_cells_prior_year,
  case when not a.sup and not pa.sup and pa.completions > 0
       then (a.completions - pa.completions) * 100.0 / pa.completions end as yoy_pct_change,
  case when not ba.sup then ba.completions end as completions_2020,
  a.n_cells_2020 as n_program_cells_2020,
  case when a.year > 2020 and not a.sup and not ba.sup and ba.completions > 0
       then (a.completions - ba.completions) * 100.0 / ba.completions end as pct_change_vs_2020
from a
left join m_level_dim l on l.level_key = a.level_key
left join m_institution_dim d on d.unitid = a.unitid
left join cellsupp cs on cs.unitid = a.unitid and cs.year = a.year and cs.level_key = a.level_key
left join a pa on pa.unitid = a.unitid and pa.level_key = a.level_key and pa.year = a.year - 1
left join a ba on ba.unitid = a.unitid and ba.level_key = a.level_key and ba.year = 2020 and a.year > 2020;

-- 3. national totals display (national aggregates, counts are all large; same <10 rule applied for safety)
create or replace table m_national_display as
with prior_fall as (
  select year,
    sum(completions) as pf_completions, sum(grad_enrollment_total_prior_fall) as pf_enrollment,
    count(*) as pf_n_institutions
  from m_inst_summary_internal
  where level_key = 'all_masters_doctoral' and grad_enrollment_total_prior_fall > 0
  group by year
)
select n.year, n.level_key,
  case n.level_key when 'all_masters_doctoral' then 'All master''s and doctoral levels (7, 17, 18, 19)'
       else l.level_label end as award_level,
  n.completions as completions_total, n.n_cells as n_program_cells, n.n_institutions,
  n.grad_enrollment_total, n.grad_enrollment_ft, n.grad_enrollment_pt, n.n_institutions_with_enrollment,
  n.matched_completions, n.matched_enrollment, n.n_matched_institutions,
  n.matched_completions * 1.0 / n.matched_enrollment as ratio_completions_to_grad_enrollment_matched,
  n.completions * 1.0 / n.grad_enrollment_total as ratio_completions_to_grad_enrollment_all,
  case when n.level_key = 'all_masters_doctoral' and n.year > 2020 then pf.pf_completions * 1.0 / pf.pf_enrollment end
    as ratio_completions_to_prior_fall_grad_enrollment_matched,
  case when n.level_key = 'all_masters_doctoral' and n.year > 2020 then pf.pf_n_institutions end as n_matched_institutions_prior_fall,
  p.completions as completions_prior_year, p.n_cells as n_program_cells_prior_year, p.n_institutions as n_institutions_prior_year,
  (n.completions - p.completions) * 100.0 / p.completions as yoy_pct_change,
  b.completions as completions_2020, b.n_cells as n_program_cells_2020, b.n_institutions as n_institutions_2020,
  case when n.year > 2020 then (n.completions - b.completions) * 100.0 / b.completions end as pct_change_vs_2020
from m_national_internal n
left join m_level_dim l on l.level_key = n.level_key
left join m_national_internal p on p.level_key = n.level_key and p.year = n.year - 1
left join m_national_internal b on b.level_key = n.level_key and b.year = 2020 and n.year > 2020
left join prior_fall pf on pf.year = n.year;

-- 4. approximate CIP2 -> NSF SED trend broad field crosswalk (mapping made by the author, NOT an official NSF crosswalk)
create or replace table m_cip2_sed as
select * from (values
  ('01', 'Agricultural sciences and natural resources'), ('03', 'Agricultural sciences and natural resources'),
  ('26', 'Biological and biomedical sciences'), ('51', 'Health sciences'),
  ('11', 'Computer and information sciences'), ('14', 'Engineering'), ('15', 'Engineering'),
  ('27', 'Mathematics and statistics'), ('40', 'Physical sciences'), ('42', 'Psychology'),
  ('45', 'Social sciences'), ('13', 'Education'), ('52', 'Business'),
  ('16', 'Humanities and arts'), ('23', 'Humanities and arts'), ('38', 'Humanities and arts'),
  ('50', 'Humanities and arts'), ('54', 'Humanities and arts')
) t(cip2, sed_broad_field);

-- 5. field (CIP2) summary display
create or replace table m_field_display as
select f.year, f.cip2, f.cip2_title, f.level_key,
  case f.level_key when 'all_masters_doctoral' then 'All master''s and doctoral levels (7, 17, 18, 19)'
       else l.level_label end as award_level,
  case when f.completions < 10 then null else f.completions end as completions_total,
  (f.completions < 10)::int as completions_suppressed,
  f.n_institutions, f.n_cells as n_program_cells,
  f.n_cells_lt10 as n_program_cells_lt10,
  f.n_cells_lt10 * 1.0 / f.n_cells as share_program_cells_lt10,
  f.completions_in_cells_lt10 * 1.0 / f.completions as share_completions_in_cells_lt10,
  f.n_cells_suppressed_incl_complementary as n_program_cells_suppressed_incl_complementary,
  case when p.completions >= 10 then p.completions end as completions_prior_year,
  p.n_cells as n_program_cells_prior_year, p.n_institutions as n_institutions_prior_year,
  case when f.completions >= 10 and p.completions >= 10
       then (f.completions - p.completions) * 100.0 / p.completions end as yoy_pct_change,
  case when b.completions >= 10 then b.completions end as completions_2020,
  b.n_cells as n_program_cells_2020, b.n_institutions as n_institutions_2020,
  case when f.year > 2020 and f.completions >= 10 and b.completions >= 10
       then (f.completions - b.completions) * 100.0 / b.completions end as pct_change_vs_2020,
  x.sed_broad_field as sed_broad_field_approx
from m_field_internal f
left join m_level_dim l on l.level_key = f.level_key
left join m_field_internal p on p.cip2 = f.cip2 and p.level_key = f.level_key and p.year = f.year - 1
left join m_field_internal b on b.cip2 = f.cip2 and b.level_key = f.level_key and b.year = 2020 and f.year > 2020
left join m_cip2_sed x on x.cip2 = f.cip2;

-- 6. NSF SED benchmark: latest year of each cycle
create or replace table m_sed_benchmark as
select m.table_number as table_id, n.cycle, n.is_newest_cycle, n.year as sed_year,
  n.field, n.field_type, n.parent_sector, n.measure,
  n.value as median_years, n.value_raw, n.footnote_marker,
  m.table_title, m.source_url
from nsf_sed_median_years n
join nsf_sed_table_meta m on m.cycle = n.cycle
where n.year = (select max(x.year) from nsf_sed_median_years x where x.cycle = n.cycle);
