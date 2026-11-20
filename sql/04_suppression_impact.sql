-- 04_suppression_impact.sql : suppression statistics by threshold x level x year (all-level row included)
create or replace table m_supp_cells_lvl as
select s.thr, s.year, l.level_key, c.unitid, c.completions, s.prim, s.comp1, s.comp2, s.suppressed
from m_cell_supp s
join m_program_cells c on c.unitid = s.unitid and c.year = s.year and c.cipcode = s.cipcode and c.awlevel = s.awlevel
join m_level_dim l on l.awlevel = s.awlevel;

create or replace table m_supp_impact as
with x as (
  select * from m_supp_cells_lvl
  union all
  select thr, year, 'all_masters_doctoral', unitid, completions, prim, comp1, comp2, suppressed from m_supp_cells_lvl
), cells as (
  select thr, year, level_key,
    count(*) as n_cells,
    sum(prim::int) as n_cells_primary_suppressed,
    sum(comp1::int) as n_cells_complementary_family,
    sum(comp2::int) as n_cells_complementary_institution,
    sum(suppressed::int) as n_cells_suppressed_total,
    sum(completions) as completions_total,
    sum(case when prim then completions else 0 end) as completions_in_primary_suppressed,
    sum(case when suppressed then completions else 0 end) as completions_in_suppressed_total,
    sum((completions = 0)::int) as n_cells_zero_count
  from x group by all
), inst as (
  select thr, year, level_key, count(*) as n_institutions,
    sum((np > 0)::int) as n_institutions_with_primary_suppressed,
    sum((ns > 0)::int) as n_institutions_with_any_suppressed,
    sum((np = n)::int) as n_institutions_all_cells_primary_suppressed,
    sum((ns = n)::int) as n_institutions_all_cells_suppressed_total
  from (select thr, year, level_key, unitid, count(*) as n, sum(prim::int) as np, sum(suppressed::int) as ns
        from x group by all) g
  group by all
)
select c.thr as threshold, c.year, c.level_key,
  c.n_cells, c.n_cells_primary_suppressed,
  c.n_cells_primary_suppressed * 1.0 / c.n_cells as share_cells_primary_suppressed,
  c.n_cells_complementary_family, c.n_cells_complementary_institution,
  c.n_cells_suppressed_total, c.n_cells_suppressed_total * 1.0 / c.n_cells as share_cells_suppressed_total,
  c.completions_total, c.completions_in_primary_suppressed,
  c.completions_in_primary_suppressed * 1.0 / c.completions_total as share_completions_in_primary_suppressed,
  c.completions_in_suppressed_total,
  c.completions_in_suppressed_total * 1.0 / c.completions_total as share_completions_in_suppressed_total,
  c.n_cells_zero_count,
  i.n_institutions, i.n_institutions_with_primary_suppressed,
  i.n_institutions_with_primary_suppressed * 1.0 / i.n_institutions as share_institutions_with_primary_suppressed,
  i.n_institutions_with_any_suppressed,
  i.n_institutions_all_cells_primary_suppressed,
  i.n_institutions_all_cells_primary_suppressed * 1.0 / i.n_institutions as share_institutions_all_cells_primary_suppressed,
  i.n_institutions_all_cells_suppressed_total,
  i.n_institutions_all_cells_suppressed_total * 1.0 / i.n_institutions as share_institutions_all_cells_suppressed_total
from cells c join inst i on i.thr = c.thr and i.year = c.year and i.level_key = c.level_key;
