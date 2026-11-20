-- 03_measures.sql : internal (unsuppressed) measures. Nothing here is published directly.
-- level_key 'all_masters_doctoral' = awlevel 7 + 17 + 18 + 19.

-- graduate enrollment per institution-year (EFALEVEL 12 total, 32 full-time, 52 part-time)
create or replace table m_inst_enrollment as
select unitid, year,
  max(case when efalevel = 12 then eftotlt end) as grad_enrollment_total,
  coalesce(max(case when efalevel = 32 then eftotlt end), 0) as grad_enrollment_ft,
  coalesce(max(case when efalevel = 52 then eftotlt end), 0) as grad_enrollment_pt
from enrollment
where efalevel in (12, 32, 52)
group by unitid, year;

-- institution x year x level totals (plus the all-level row; the all-level row also exists for enrollment-only institutions)
create or replace table m_inst_level_totals as
select unitid, year, coalesce(level_key, 'all_masters_doctoral') as level_key,
  sum(completions) as completions, count(*) as n_cells
from m_program_cells
group by grouping sets ((unitid, year, level_key), (unitid, year));

insert into m_inst_level_totals
select e.unitid, e.year, 'all_masters_doctoral', 0, 0
from m_inst_enrollment e
where not exists (select 1 from m_inst_level_totals t
                  where t.unitid = e.unitid and t.year = e.year and t.level_key = 'all_masters_doctoral');

create or replace table m_inst_summary_internal as
select t.unitid, t.year, t.level_key, t.completions, t.n_cells,
  p.completions as completions_prior_year, coalesce(p.n_cells, 0) as n_cells_prior_year,
  b.completions as completions_2020, coalesce(b.n_cells, 0) as n_cells_2020,
  e.grad_enrollment_total, e.grad_enrollment_ft, e.grad_enrollment_pt,
  ep.grad_enrollment_total as grad_enrollment_total_prior_fall
from m_inst_level_totals t
left join m_inst_level_totals p on p.unitid = t.unitid and p.level_key = t.level_key and p.year = t.year - 1
left join m_inst_level_totals b on b.unitid = t.unitid and b.level_key = t.level_key and b.year = 2020 and t.year > 2020
left join m_inst_enrollment e on e.unitid = t.unitid and e.year = t.year
left join m_inst_enrollment ep on ep.unitid = t.unitid and ep.year = t.year - 1;

-- national totals by year x level (internal)
create or replace table m_national_internal as
with cells as (
  select year, coalesce(level_key, 'all_masters_doctoral') as level_key,
    sum(completions) as completions, count(*) as n_cells, count(distinct unitid) as n_institutions
  from m_program_cells group by grouping sets ((year, level_key), (year))
), enr as (
  select year, sum(grad_enrollment_total) as grad_enrollment_total, sum(grad_enrollment_ft) as grad_enrollment_ft,
    sum(grad_enrollment_pt) as grad_enrollment_pt, count(*) as n_institutions_with_enrollment
  from m_inst_enrollment group by year
), matched as (
  -- institutions that have BOTH graduate enrollment (>0) and an all-level completions row
  select e.year,
    sum(e.grad_enrollment_total) as matched_enrollment,
    sum(t.completions) as matched_completions,
    count(*) as n_matched_institutions
  from m_inst_enrollment e
  join m_inst_level_totals t on t.unitid = e.unitid and t.year = e.year and t.level_key = 'all_masters_doctoral'
  where e.grad_enrollment_total > 0
  group by e.year
)
select c.year, c.level_key, c.completions, c.n_cells, c.n_institutions,
  case when c.level_key = 'all_masters_doctoral' then enr.grad_enrollment_total end as grad_enrollment_total,
  case when c.level_key = 'all_masters_doctoral' then enr.grad_enrollment_ft end as grad_enrollment_ft,
  case when c.level_key = 'all_masters_doctoral' then enr.grad_enrollment_pt end as grad_enrollment_pt,
  case when c.level_key = 'all_masters_doctoral' then enr.n_institutions_with_enrollment end as n_institutions_with_enrollment,
  case when c.level_key = 'all_masters_doctoral' then m.matched_completions end as matched_completions,
  case when c.level_key = 'all_masters_doctoral' then m.matched_enrollment end as matched_enrollment,
  case when c.level_key = 'all_masters_doctoral' then m.n_matched_institutions end as n_matched_institutions
from cells c
left join enr on enr.year = c.year
left join matched m on m.year = c.year;

-- field (CIP2) x level x year national totals (internal), primary suppression at 10 for the shares
create or replace table m_field_internal as
with joined as (
  select c.year, c.cip2, c.cip2_title, c.level_key, c.unitid, c.completions,
    s.prim, s.suppressed
  from m_program_cells c
  join m_cell_supp s on s.thr = 10 and s.unitid = c.unitid and s.year = c.year
                    and s.cipcode = c.cipcode and s.awlevel = c.awlevel
)
select year, cip2, any_value(cip2_title) as cip2_title, coalesce(level_key, 'all_masters_doctoral') as level_key,
  sum(completions) as completions, count(*) as n_cells, count(distinct unitid) as n_institutions,
  sum(prim::int) as n_cells_lt10, sum(suppressed::int) as n_cells_suppressed_incl_complementary,
  sum(case when prim then completions else 0 end) as completions_in_cells_lt10
from joined
group by grouping sets ((year, cip2, level_key), (year, cip2));
