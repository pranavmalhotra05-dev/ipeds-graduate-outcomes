-- 02_suppression_init.sql : empty cell-level suppression table (filled per threshold by 02_suppression_run.sql)
drop table if exists m_cell_supp;
create table m_cell_supp (
  thr integer, unitid bigint, year bigint, cipcode varchar, awlevel bigint,
  prim boolean, comp1 boolean, comp2 boolean, suppressed boolean
);
