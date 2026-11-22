#!/usr/bin/env python3
"""
scripts/merge_cscint_local.py
-----------------------------
Fast multi-processed local merger for cscint runs and category files.
Merges individual run partition files (part_*.root) from:
  /eos/user/i/idioniso/Timing/cscint_parts/catIII/run<RUN>/
into:
  /eos/user/i/idioniso/Timing/cscint/runs/run<RUN>.root
and optionally creates:
  /eos/user/i/idioniso/Timing/cscint/categories/catIII_<YEAR>.root

Usage:
  # Merge only the missing 2024 runs (using 4 parallel jobs):
  python3 scripts/merge_cscint_local.py -y 2024 -j 4

  # Merge specific runs:
  python3 scripts/merge_cscint_local.py -r 9094,9269,9361 -j 3

  # Force re-merge even if runs already exist:
  python3 scripts/merge_cscint_local.py -y 2024 --force

  # Merge all years:
  python3 scripts/merge_cscint_local.py -y all -j 4
"""

import os
import sys
import glob
import time
import shutil
import argparse
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

RUNS_BY_YEAR = {
    2023: [6079, 6568, 6574, 6577, 6590, 6593, 6596, 6640, 6663, 6667],
    2024: [8638, 8724, 9094, 9269, 9361, 9436, 9622, 9649, 9685, 9880],
    2025: [11124, 11193, 11241, 11555, 11720, 11744, 11747, 12205, 12213, 12217],
    2026: [13085, 13098, 13101, 13104, 13162, 13406, 13480, 13503, 13508, 13520],
}

DEFAULT_PARTS_DIR = "/eos/user/i/idioniso/Timing/cscint_parts/catIII"
DEFAULT_RUNS_DIR = "/eos/user/i/idioniso/Timing/cscint/runs"
DEFAULT_CATS_DIR = "/eos/user/i/idioniso/Timing/cscint/categories"


def merge_single_run(run_nr: int, parts_dir: str, runs_dir: str, threads_per_job: int = 2, force: bool = False):
    """Merges all partitions for a single run into runs/run<RUN>.root via local /tmp scratch."""
    out_file = os.path.join(runs_dir, f"run{run_nr}.root")
    
    # Check if already exists
    if not force and os.path.isfile(out_file):
        sz = os.path.getsize(out_file)
        if sz > 1_000_000:
            return run_nr, True, f"Already exists ({sz / 1e6:.1f} MB), skipped.", 0.0

    run_parts_dir = os.path.join(parts_dir, f"run{run_nr}")
    if not os.path.isdir(run_parts_dir):
        return run_nr, False, f"Directory not found: {run_parts_dir}", 0.0

    part_files = sorted(glob.glob(os.path.join(run_parts_dir, "part_*.root")))
    if not part_files:
        return run_nr, False, f"No partition files in {run_parts_dir}", 0.0

    scratch_out = f"/tmp/cscint_run{run_nr}_{os.getpid()}_{int(time.time())}.root"
    t0 = time.time()
    
    cmd = ["hadd", "-f", "-k", f"-j{threads_per_job}", scratch_out] + part_files
    try:
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode != 0 and not os.path.exists(scratch_out):
            return run_nr, False, f"hadd failed: {res.stderr.strip()[:200]}", time.time() - t0

        if not os.path.exists(scratch_out) or os.path.getsize(scratch_out) < 1000:
            return run_nr, False, "Resulting ROOT file is missing or empty", time.time() - t0

        # Move to target EOS path atomically
        tmp_target = f"{out_file}.tmp"
        shutil.copyfile(scratch_out, tmp_target)
        os.replace(tmp_target, out_file)
        
        final_size = os.path.getsize(out_file)
        elapsed = time.time() - t0
        return run_nr, True, f"Merged {len(part_files)} partitions -> {final_size / 1e6:.1f} MB in {elapsed:.1f}s", elapsed

    except Exception as e:
        return run_nr, False, f"Exception: {e}", time.time() - t0
    finally:
        if os.path.exists(scratch_out):
            try:
                os.remove(scratch_out)
            except OSError:
                pass


def merge_category_file(year: int, runs_dir: str, cats_dir: str, threads: int = 4):
    """Combines the 10 individual run ROOT files of a year into catIII_<YEAR>.root."""
    run_list = RUNS_BY_YEAR.get(year, [])
    if not run_list:
        print(f"[ERROR] No runs defined for year {year}")
        return False

    cat_target = os.path.join(cats_dir, f"catIII_{year}.root")
    run_files = []
    missing = []
    for r in run_list:
        rf = os.path.join(runs_dir, f"run{r}.root")
        if os.path.isfile(rf) and os.path.getsize(rf) > 1_000_000:
            run_files.append(rf)
        else:
            missing.append(r)

    if missing:
        print(f"[WARNING] Cannot merge catIII_{year}.root: missing run files for {missing}")
        return False

    scratch_cat = f"/tmp/catIII_{year}_{os.getpid()}_{int(time.time())}.root"
    t0 = time.time()
    print(f"\n======================================================================")
    print(f" Merging Category File: catIII_{year}.root from {len(run_files)} runs...")
    print(f"======================================================================")
    
    cmd = ["hadd", "-f", "-k", f"-j{threads}", scratch_cat] + run_files
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
    if res.returncode != 0 and not os.path.exists(scratch_cat):
        print(f"[ERROR] Category hadd failed: {res.stderr.strip()[:300]}")
        return False

    tmp_target = f"{cat_target}.tmp"
    shutil.copyfile(scratch_cat, tmp_target)
    os.replace(tmp_target, cat_target)
    if os.path.exists(scratch_cat):
        os.remove(scratch_cat)

    final_size = os.path.getsize(cat_target)
    elapsed = time.time() - t0
    print(f"[SUCCESS] Generated {cat_target} ({final_size / 1e6:.1f} MB in {elapsed:.1f}s)")
    return True


def main():
    parser = argparse.ArgumentParser(description="Multi-processed local merger for cscint runs and category files.")
    parser.add_argument("-y", "--year", type=str, default="2024", choices=["2023", "2024", "2025", "2026", "all"],
                        help="Year to process (default: 2024)")
    parser.add_argument("-r", "--runs", type=str, default=None,
                        help="Comma-separated list of specific run numbers (e.g. 9094,9269)")
    parser.add_argument("-j", "--jobs", type=int, default=4,
                        help="Number of concurrent run merges (default: 4)")
    parser.add_argument("-t", "--threads-per-job", type=int, default=2,
                        help="Number of hadd threads per run merge (default: 2)")
    parser.add_argument("-f", "--force", action="store_true",
                        help="Force re-merge runs even if already present")
    parser.add_argument("--skip-category", action="store_true",
                        help="Do not merge the year category file (only create run files)")
    parser.add_argument("--category-only", action="store_true",
                        help="Skip partition merging and only create the year category file")
    parser.add_argument("--parts-dir", type=str, default=DEFAULT_PARTS_DIR,
                        help=f"Directory containing run<RUN>/part_*.root (default: {DEFAULT_PARTS_DIR})")
    parser.add_argument("--runs-dir", type=str, default=DEFAULT_RUNS_DIR,
                        help=f"Destination directory for run<RUN>.root (default: {DEFAULT_RUNS_DIR})")
    parser.add_argument("--cats-dir", type=str, default=DEFAULT_CATS_DIR,
                        help=f"Destination directory for category files (default: {DEFAULT_CATS_DIR})")
    args = parser.parse_args()

    os.makedirs(args.runs_dir, exist_ok=True)
    os.makedirs(args.cats_dir, exist_ok=True)

    years_to_process = [2023, 2024, 2025, 2026] if args.year == "all" else [int(args.year)]

    runs_to_process = []
    if args.runs:
        for r_s in args.runs.split(","):
            r_s = r_s.strip()
            if r_s.isdigit():
                runs_to_process.append(int(r_s))
    else:
        for y in years_to_process:
            runs_to_process.extend(RUNS_BY_YEAR.get(y, []))

    print("======================================================================")
    print(f" Local Multi-Process cscint Merger")
    print(f" Target Year(s)     : {args.year}")
    print(f" Target Runs        : {len(runs_to_process)} runs: {runs_to_process}")
    print(f" Parallel Jobs      : {args.jobs} concurrent runs")
    print(f" Threads per Run    : {args.threads_per_job} (hadd -j{args.threads_per_job})")
    print(f" Overwrite (force)  : {args.force}")
    print(f" Runs Directory     : {args.runs_dir}")
    print(f" Partitions Dir     : {args.parts_dir}")
    print("======================================================================")

    if not args.category_only and runs_to_process:
        start_time = time.time()
        successes, failures = 0, 0
        with ProcessPoolExecutor(max_workers=args.jobs) as executor:
            future_to_run = {
                executor.submit(
                    merge_single_run, r, args.parts_dir, args.runs_dir, args.threads_per_job, args.force
                ): r for r in runs_to_process
            }
            for future in as_completed(future_to_run):
                run_nr, ok, msg, elap = future.result()
                tag = "[DONE]" if ok else "[FAIL]"
                print(f" {tag} Run {run_nr:<5} : {msg}", flush=True)
                if ok:
                    successes += 1
                else:
                    failures += 1

        total_elapsed = time.time() - start_time
        print(f"\n[SUMMARY] Runs processed: {successes} succeeded, {failures} failed in {total_elapsed / 60:.1f} min.")

    # Category Merging
    if not args.skip_category:
        for y in years_to_process:
            merge_category_file(y, args.runs_dir, args.cats_dir, threads=min(8, args.jobs * args.threads_per_job))


if __name__ == "__main__":
    main()
