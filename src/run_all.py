"""run_all.py - rebuild the whole project with one command.

Runs, in order, each with the Python interpreter that launched this script and the isolated flag -I:
  01_ingest.py, 02_build_measures.py, 03_reconcile.py, 04_build_dashboard.py,
  05_build_tableau_public.py (optional, only if present), 06_make_charts.py
Stops at the first failing step and exits with that step's return code.

Run:  python -I src/run_all.py
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ["01_ingest.py", "02_build_measures.py", "03_reconcile.py", "04_build_dashboard.py",
         "05_build_tableau_public.py", "06_make_charts.py"]
OPTIONAL = {"05_build_tableau_public.py"}  # skipped when the file is not present


def main() -> int:
    t_all = time.time()
    for name in STEPS:
        script = ROOT / "src" / name
        if not script.exists() and name in OPTIONAL:
            print(f"[run_all] skipping optional step (not present): {name}", flush=True)
            continue
        if not script.exists():
            print(f"[run_all] missing script: {script}", file=sys.stderr)
            return 2
        print(f"[run_all] >>> {name}", flush=True)
        t0 = time.time()
        result = subprocess.run([sys.executable, "-I", str(script)], cwd=ROOT)
        secs = time.time() - t0
        if result.returncode != 0:
            print(f"[run_all] FAILED: {name} (exit code {result.returncode}) after {secs:.0f}s; stopping.", file=sys.stderr)
            return result.returncode
        print(f"[run_all] done: {name} in {secs:.0f}s", flush=True)
    print(f"[run_all] all steps finished in {time.time() - t_all:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
