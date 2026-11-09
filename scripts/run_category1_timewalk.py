#!/usr/bin/env python3
"""
Batch runner for TimeWalk calibration on Category I runs with > 3M entries.

Executes:
    /afs/cern.ch/work/i/idioniso/sndVetoUS/run_TimeWalk.sh <run_number> 1000000 10
"""

import os
import sys
import argparse
import subprocess
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run TimeWalk calibration for Category I runs (>3M events)."
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="/afs/cern.ch/work/i/idioniso/sndVetoUS/pp2022.csv",
        help="Path to pp2022.csv metadata file",
    )
    parser.add_argument(
        "--script",
        type=str,
        default="/afs/cern.ch/work/i/idioniso/sndVetoUS/run_TimeWalk.sh",
        help="Path to run_TimeWalk.sh script",
    )
    parser.add_argument(
        "--events",
        type=int,
        default=1000000,
        help="Number of events per run (default: 1000000)",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=10,
        help="Number of parallel worker jobs (default: 10)",
    )
    parser.add_argument(
        "--min-entries",
        type=int,
        default=3000000,
        help="Minimum total entries in run to include (default: 3000000)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    parser.add_argument(
        "--start-from",
        type=int,
        default=None,
        help="Optional run number to start/resume from",
    )
    parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Maximum number of runs to process",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.isfile(args.csv):
        sys.exit(f"Error: CSV file not found at {args.csv}")

    if not os.path.isfile(args.script):
        sys.exit(f"Error: Script not found at {args.script}")

    df = pd.read_csv(args.csv)

    # Resolve column names dynamically
    col_run = [c for c in df.columns if "run" in c.lower()][0]
    col_entries = [c for c in df.columns if "entries" in c.lower()][0]
    col_cat = [c for c in df.columns if "category" in c.lower()][0]

    # Filter for Category I runs with entries > min_entries
    mask = (df[col_cat].astype(str).str.strip() == "I") & (df[col_entries] > args.min_entries)
    filtered_df = df[mask].sort_values(by=col_run).reset_index(drop=True)

    runs = filtered_df[col_run].tolist()

    if args.start_from is not None:
        runs = [r for r in runs if r >= args.start_from]

    if args.max_runs is not None and args.max_runs > 0:
        runs = runs[:args.max_runs]

    print(f"Found {len(runs)} Category I runs with > {args.min_entries:,} entries to process.")

    failed_runs = []
    completed_runs = []

    for idx, run in enumerate(runs, 1):
        cmd = [args.script, str(run), str(args.events), str(args.jobs)]
        cmd_str = " ".join(cmd)

        print(f"\n[{idx}/{len(runs)}] Executing: {cmd_str}")

        if args.dry_run:
            continue

        try:
            res = subprocess.run(cmd, check=True)
            completed_runs.append(run)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Run {run} failed with exit code {e.returncode}")
            failed_runs.append((run, e.returncode))
        except KeyboardInterrupt:
            print("\nExecution interrupted by user.")
            break

    print("\n" + "=" * 60)
    print("Execution Summary:")
    print(f"  Total target runs: {len(runs)}")
    print(f"  Completed successfully: {len(completed_runs)}")
    print(f"  Failed runs: {len(failed_runs)}")
    if failed_runs:
        print(f"  Failed run list: {failed_runs}")
    print("=" * 60)


if __name__ == "__main__":
    main()
