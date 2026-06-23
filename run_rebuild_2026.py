#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, subprocess, sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = ROOT / ".venv" / "Scripts" / "python.exe"
LOG = ROOT / "output" / "rebuild_2026_log.txt"

def log(msg):
    line = "[{0}] {1}".format(datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def run_step(name, args, log_file):
    log(name)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    with log_file.open("w", encoding="utf-8") as out:
        proc = subprocess.run([str(PY), "-u"] + args, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT, env=env)
    if proc.returncode != 0:
        log("FAILED {0} exit={1}".format(name, proc.returncode))
        sys.exit(proc.returncode)
    log("OK {0}".format(name))

def main():
    start = sys.argv[1] if len(sys.argv) > 1 else "all"
    log("=== REBUILD from phase {0} ===".format(start))
    if start in ("1", "all"):
        run_step("Phase 1: EIS discovery", ["run_full_pipeline.py", "--discovery-only"], ROOT / "output/discovery_2026_log.txt")
    if start in ("2", "all"):
        run_step("Phase 2: Rosatom full crawl", ["-m", "procurement.rosatom_full_scan"], ROOT / "output/rosatom_full_log.txt")
    if start in ("2", "3", "all"):
        run_step("Phase 3+4: Bothub + enrich", ["run_full_pipeline.py", "--skip-discovery", "--skip-rosatom-detail"], ROOT / "output/pipeline_bothub_2026_log.txt")
    log("=== REBUILD DONE ===")

if __name__ == "__main__":
    sys.exit(main())