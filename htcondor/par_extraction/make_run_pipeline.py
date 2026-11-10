#!/usr/bin/env python3
"""
make_run_pipeline.py
--------------------
Generates DAGMan and args files to run full-statistics 2-stage calibration
pipelines for any arbitrary run number.

Usage:
  python3 make_run_pipeline.py -r <run_number> [-n <total_events>] [-j <n_jobs>] [-f <flavour>]
"""

import os
import argparse
import glob

def find_run_events(run_nr):
    # Try reading from pp2022.csv if available
    csv_paths = [
        "/afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/par_drift/pp2022.csv",
        "/eos/user/i/idioniso/Timing/pp2022.csv",
        "/eos/user/i/idioniso/Timing/runs_2022_physics.csv"
    ]
    for cp in csv_paths:
        if os.path.exists(cp):
            try:
                import pandas as pd
                df = pd.read_csv(cp)
                run_col = [c for c in df.columns if "run" in c.lower()][0]
                ent_col = [c for c in df.columns if "entries" in c.lower() or "event" in c.lower()][0]
                row = df[df[run_col] == run_nr]
                if not row.empty:
                    val = int(row[ent_col].values[0])
                    if val > 0:
                        return val
            except Exception:
                pass
    return None

def main():
    parser = argparse.ArgumentParser(description="Generate DAGMan pipeline for an arbitrary run")
    parser.add_argument("-r", "--run", required=True, type=int, help="Run number (e.g. 5100, 6640)")
    parser.add_argument("-n", "--events", type=int, default=None, help="Total events to partition (auto-detected if omitted)")
    parser.add_argument("-j", "--jobs", type=int, default=250, help="Number of parallel jobs (default: 250)")
    parser.add_argument("-f", "--flavour", type=str, default="workday", help="HTCondor flavour (default: workday)")
    args = parser.parse_args()

    run = args.run
    n_jobs = args.jobs
    flavour = args.flavour
    total_events = args.events

    if total_events is None:
        total_events = find_run_events(run)
        if total_events is None:
            print(f"[ERROR] Could not auto-detect events for Run {run}. Please specify with -n <total_events>.")
            exit(1)
        print(f"[INFO] Auto-detected {total_events:,} events for Run {run}.")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    args_file_name = f"args_run{run}_{n_jobs}jobs.txt"
    args_file_path = os.path.join(script_dir, args_file_name)
    dag_file_name = f"run{run}_pipeline.dag"
    dag_file_path = os.path.join(script_dir, dag_file_name)
    submit_script_name = f"submit_dag_run{run}.sh"
    submit_script_path = os.path.join(script_dir, submit_script_name)

    # 1. Generate partition args file
    per_job = total_events // n_jobs
    rem = total_events % n_jobs
    lines = []
    curr = 0
    for i in range(n_jobs):
        n_ev = per_job + (rem if i == n_jobs - 1 else 0)
        lines.append(f"{i} {curr} {n_ev}\n")
        curr += per_job

    with open(args_file_path, "w") as f:
        f.writelines(lines)
    print(f"[1/3] Created partition file: {args_file_path} ({n_jobs} jobs, ~{per_job:,} ev/job)")

    # 2. Generate DAG file
    run_str = f"{run:06d}"
    out_dir = f"/eos/user/i/idioniso/Timing/run{run_str}"
    dag_content = f"""# ==============================================================================
# HTCondor DAGMan Workflow: Full Two-Stage TimeWalk Pipeline for Run {run}
# Generated automatically by make_run_pipeline.py
# Total Events : {total_events:,} partitioned across {n_jobs} jobs
# Output       : {out_dir}
# ==============================================================================

# Stage 1: Parallel c_scint speed accumulation ({n_jobs} jobs)
JOB STAGE1_SPEED par_extraction.sub
VARS STAGE1_SPEED run="{run}" out_dir="{out_dir}" args_file="{args_file_name}" flavour="{flavour}" stage_mode="speed"

# Stage 1 Merger & Fit (produces run{run_str}_cscintvalues.json)
JOB MERGE_FIT_SPEED merge_worker.sub
VARS MERGE_FIT_SPEED run="{run}" mode_arg="--fit-speed" mode_name="fit_speed" n_expected="{n_jobs}"

# Stage 2: Parallel Time-Walk accumulation using Stage 1 c_scint ({n_jobs} jobs)
JOB STAGE2_TW par_extraction.sub
VARS STAGE2_TW run="{run}" out_dir="{out_dir}" args_file="{args_file_name}" flavour="{flavour}" stage_mode="full"

# Stage 2 Merger & Final Fit (produces final ROOT & consolidated JSON)
JOB MERGE_FIT_FINAL merge_worker.sub
VARS MERGE_FIT_FINAL run="{run}" mode_arg="" mode_name="fit_final" n_expected="{n_jobs}"

# Dependencies
PARENT STAGE1_SPEED   CHILD MERGE_FIT_SPEED
PARENT MERGE_FIT_SPEED CHILD STAGE2_TW
PARENT STAGE2_TW      CHILD MERGE_FIT_FINAL
"""
    with open(dag_file_path, "w") as f:
        f.write(dag_content)
    print(f"[2/3] Created DAGMan file   : {dag_file_path}")

    # 3. Generate wrapper submit bash script
    sh_content = f"""#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
cd "${{SCRIPT_DIR}}"

mkdir -p out err log "{out_dir}/parallel_parts"

DAG_FILE="${{SCRIPT_DIR}}/{dag_file_name}"

echo "=========================================================="
echo " Submitting Run {run} Full Calibration DAGMan Workflow"
echo " DAG File  : ${{DAG_FILE}}"
echo " Total     : 2 Stages, $(( {n_jobs} * 2 + 2 )) executions"
echo " Mode      : Fully Automated End-to-End Pipeline"
echo "=========================================================="

if [ "$1" = "--dry-run" ]; then
    echo "[Dry-Run Mode] Command that would be executed on lxplus:"
    echo "condor_submit_dag ${{DAG_FILE}}"
    exit 0
fi

if ! command -v condor_submit_dag >/dev/null 2>&1; then
    echo "ERROR: 'condor_submit_dag' not found in PATH." >&2
    echo "Please execute this script from an lxplus node (e.g., ssh lxplus.cern.ch)." >&2
    exit 1
fi

condor_submit_dag "${{DAG_FILE}}"

echo ""
echo "DAG submitted! You can monitor the workflow with:"
echo "  condor_q -dag"
echo "  tail -f ${{DAG_FILE}}.dagman.out"
"""
    with open(submit_script_path, "w") as f:
        f.write(sh_content)
    os.chmod(submit_script_path, 0o755)
    print(f"[3/3] Created submit script : {submit_script_path}")
    print(f"\nReady to submit! Run from lxplus:\n  ./{submit_script_name}")

if __name__ == "__main__":
    main()
