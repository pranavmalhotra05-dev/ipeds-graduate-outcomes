-- 01_base.sql : analysis base. One row per program cell = institution x CIP6 x award level x year.
-- Inputs registered by Python: m_cip2_dim(cip2, cip2_title), m_carnegie_dim(vintage, code, label)

create or replace table m_level_dim as
select * from (values
  (7,  'masters',                'Master''s degree',                         1),
  (17, 'research_doctorate',     'Doctor''s degree - research/scholarship',  2),
  (18, 'professional_doctorate', 'Doctor''s degree - professional practice', 3),
  (19, 'other_doctorate',        'Doctor''s degree - other',                 4)
) t(awlevel, level_key, level_label, sort_order);

create or replace table m_program_cells as
select
  c.unitid, c.year, c.cipcode, left(c.cipcode, 2) as cip2,
  c.awlevel, l.level_key, l.level_label,
  c.ctotalt as completions, c.ctotalm as completions_men, c.ctotalw as completions_women,
  c.xctotalt as imputation_flag,
  i.instnm, i.stabbr, i.control,
  case i.control when 1 then 'Public' when 2 then 'Private not-for-profit'
                 when 3 then 'Private for-profit' else 'Not available' end as control_label,
  i.sector, i.carnegie_basic, i.carnegie_basic_vintage,
  k.label as carnegie_label,
  (i.unitid is null) as hd_join_miss,
  t.title as cip_title,
  d.cip2_title
from completions c
join m_level_dim l on l.awlevel = c.awlevel
left join institutions i on i.unitid = c.unitid and i.year = c.year
left join m_carnegie_dim k on k.vintage = cast(i.carnegie_basic_vintage as varchar) and k.code = i.carnegie_basic
left join cip_titles t on t.cipcode = c.cipcode and t.cip_level = 'program'
left join m_cip2_dim d on d.cip2 = left(c.cipcode, 2)
where c.majornum = 1 and c.cipcode <> '99';

-- institution dimension: all institutions seen in the base or in graduate enrollment, attributes from latest HD year available
create or replace table m_institution_dim as
with ids as (
  select unitid, min(year) as first_year, max(year) as last_year, count(distinct year) as n_years_with_completions
  from m_program_cells group by unitid
), enr_ids as (select distinct unitid from enrollment),
all_ids as (
  select unitid from ids union select unitid from enr_ids
), last_hd as (
  select i.*, row_number() over (partition by i.unitid order by i.year desc) as rn
  from institutions i where i.year between 2020 and 2023
)
select a.unitid, h.instnm, h.stabbr, h.control,
  case h.control when 1 then 'Public' when 2 then 'Private not-for-profit'
                 when 3 then 'Private for-profit' else 'Not available' end as control_label,
  h.sector, h.carnegie_basic, h.carnegie_basic_vintage, k.label as carnegie_label,
  h.year as hd_year_used,
  ids.first_year as first_completions_year, ids.last_year as last_completions_year,
  coalesce(ids.n_years_with_completions, 0) as n_years_with_completions,
  (a.unitid in (select unitid from enr_ids)) as has_graduate_enrollment
from all_ids a
left join ids on ids.unitid = a.unitid
left join last_hd h on h.unitid = a.unitid and h.rn = 1
left join m_carnegie_dim k on k.vintage = cast(h.carnegie_basic_vintage as varchar) and k.code = h.carnegie_basic;
