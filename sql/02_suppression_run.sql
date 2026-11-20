-- 02_suppression_run.sql : run once per threshold, ${thr} replaced by Python.
-- primary   : cell count < threshold (zero counts included)
-- comp1     : within institution x level x year x CIP2 family, if exactly one cell is primary-suppressed,
--             also suppress the next-smallest remaining cell (ties broken by CIP code)
-- comp2     : within institution x level x year, if exactly one cell is suppressed after comp1,
--             also suppress the next-smallest remaining cell (so published institution-level totals cannot back-derive it)
create or replace temp table t_s1 as
select unitid, year, awlevel, cip2, cipcode, completions,
  (completions < ${thr}) as prim,
  sum((completions < ${thr})::int) over (partition by unitid, year, awlevel, cip2) as n_prim_family
from m_program_cells;

create or replace temp table t_s2 as
select *,
  (n_prim_family = 1 and not prim and
   row_number() over (partition by unitid, year, awlevel, cip2 order by prim, completions, cipcode) = 1) as comp1
from t_s1;

create or replace temp table t_s3 as
select *, (prim or comp1) as supp1,
  sum((prim or comp1)::int) over (partition by unitid, year, awlevel) as n_supp_inst_level
from t_s2;

insert into m_cell_supp
select ${thr}, unitid, year, cipcode, awlevel, prim, comp1,
  (n_supp_inst_level = 1 and not supp1 and
   row_number() over (partition by unitid, year, awlevel order by supp1, completions, cipcode) = 1) as comp2,
  false
from t_s3;

update m_cell_supp set suppressed = (prim or comp1 or comp2) where thr = ${thr};
