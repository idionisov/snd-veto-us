#!/usr/bin/env python3
"""
Batch runner for TimeWalk calibration on Category I or II runs.

Executes:
    /afs/cern.ch/work/i/idioniso/snd-veto-us/scripts/run_TimeWalk.sh <run_number> <events> <jobs>

After calibration, automatically extracts and plots the DS and SciFi reference
time distributions (reft-DS and reft-SF) using matplotlib + ddfUtils.mpl_styling.
"""

import os
import sys
import argparse
import subprocess
import glob
import pandas as pd


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run TimeWalk calibration for Category I / II runs (>3M events)."
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        default="I",
        choices=["I", "II", "1", "2"],
        help="Category to process: 'I' (default) or 'II'",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default="/afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/par_drift/pp2022.csv",
        help="Path to pp2022.csv metadata file",
    )
    parser.add_argument(
        "--script",
        type=str,
        default=None,
        help="Path to run_TimeWalk.sh script (default auto-detected)",
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
        "--out-base",
        type=str,
        default="/eos/user/i/idioniso/Timing",
        help="Base output directory for timing files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print commands without executing them",
    )
    parser.add_argument(
        "--plot-only",
        action="store_true",
        help="Skip calibration execution and only generate reference time plots",
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


def plot_reference_times(run_nr, out_dir):
    """Plot reft-DS and reft-SF distributions for the given run using uproot & matplotlib."""
    try:
        import uproot
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import ddfUtils.mpl_styling as dms
    except ImportError as e:
        print(f"Warning: Cannot plot reference times due to missing module: {e}")
        return False

    root_file = os.path.join(out_dir, "timewalk_calibration.root")
    if not os.path.exists(root_file):
        root_file = os.path.join(out_dir, "merged_raw_histograms.root")
    if not os.path.exists(root_file):
        return False

    try:
        with uproot.open(root_file) as f:
            has_ds = "reft-DS" in f
            has_sf = "reft-SF" in f

            if not has_ds and not has_sf:
                return False

            fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))

            # Left panel: DS horizontal reference time
            if has_ds:
                counts_ds, edges_ds = f["reft-DS"].to_numpy()
                axes[0].step(edges_ds[:-1], counts_ds, where="post", color="navy", lw=1.5)
                axes[0].set_yscale("log")
                axes[0].set_xlim(0, 45)
                axes[0].set_xlabel(r"$t_0^{\mathrm{DS}}$: DS average time [ns]", fontsize=13)
                axes[0].set_ylabel("Counts", fontsize=13)
                axes[0].grid(True, which="both", linestyle="--", alpha=0.35)
                dms.add_label(mainText="SND@LHC", extraText="Internal", suppText=f"Run {run_nr} (DS)", ax=axes[0])
            else:
                axes[0].text(0.5, 0.5, "reft-DS not present", ha="center", va="center")

            # Right panel: SciFi reference time
            if has_sf:
                counts_sf, edges_sf = f["reft-SF"].to_numpy()
                axes[1].step(edges_sf[:-1], counts_sf, where="post", color="crimson", lw=1.5)
                axes[1].set_yscale("log")
                axes[1].set_xlim(-25, 25)
                axes[1].set_xlabel(r"$t_0^{\mathrm{SF}}$: SciFi average time [ns]", fontsize=13)
                axes[1].set_ylabel("Counts", fontsize=13)
                axes[1].grid(True, which="both", linestyle="--", alpha=0.35)
                dms.add_label(mainText="SND@LHC", extraText="Internal", suppText=f"Run {run_nr} (SciFi)", ax=axes[1])
            else:
                axes[1].text(0.5, 0.5, "reft-SF not present", ha="center", va="center")

            plt.tight_layout()
            out_png = os.path.join(out_dir, f"run{run_nr:06d}_reference_times.png")
            plt.savefig(out_png, dpi=150)
            plt.close(fig)
            print(f"  -> Reference times plot saved to: {out_png}")
            return True
    except Exception as err:
        print(f"Warning: Failed to plot reference times for run {run_nr}: {err}")
        return False


def main():
    args = parse_args()

    # Normalize category string
    category = "I" if args.category in ("I", "1") else "II"

    # Auto-resolve script path if not provided
    script_path = args.script
    if not script_path:
        cand1 = "/afs/cern.ch/work/i/idioniso/snd-veto-us/scripts/run_TimeWalk.sh"
        cand2 = "/afs/cern.ch/work/i/idioniso/sndVetoUS/scripts/run_TimeWalk.sh"
        cand3 = "/afs/cern.ch/work/i/idioniso/sndVetoUS/run_TimeWalk.sh"
        for c in (cand1, cand2, cand3):
            if os.path.isfile(c):
                script_path = c
                break

    if not args.plot_only:
        if not script_path or not os.path.isfile(script_path):
            sys.exit(f"Error: run_TimeWalk.sh script not found at {script_path}")

    # Auto-resolve CSV path
    csv_path = args.csv
    if not os.path.isfile(csv_path):
        cands = [
            "/afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/par_drift/pp2022.csv",
            "/afs/cern.ch/work/i/idioniso/sndVetoUS/htcondor/par_drift/pp2022.csv",
            "/afs/cern.ch/work/i/idioniso/sndVetoUS/pp2022.csv",
            "/afs/cern.ch/work/i/idioniso/snd-veto-us/pp2022.csv",
        ]
        for c in cands:
            if os.path.isfile(c):
                csv_path = c
                break

    if not os.path.isfile(csv_path):
        sys.exit(f"Error: CSV file not found at {csv_path}")

    df = pd.read_csv(csv_path)

    # Resolve column names dynamically
    col_run = [c for c in df.columns if "run" in c.lower()][0]
    col_entries = [c for c in df.columns if "entries" in c.lower()][0]
    col_cat = [c for c in df.columns if "category" in c.lower()][0]

    # Filter for selected Category runs with entries > min_entries
    mask = (df[col_cat].astype(str).str.strip() == category) & (df[col_entries] > args.min_entries)
    filtered_df = df[mask].sort_values(by=col_run).reset_index(drop=True)

    runs = filtered_df[col_run].tolist()

    if args.start_from is not None:
        runs = [r for r in runs if r >= args.start_from]

    if args.max_runs is not None and args.max_runs > 0:
        runs = runs[:args.max_runs]

    print(f"Found {len(runs)} Category {category} runs with > {args.min_entries:,} entries to process.")

    failed_runs = []
    completed_runs = []

    for idx, run in enumerate(runs, 1):
        out_dir = os.path.join(args.out_base, f"run{run:06d}")

        if args.plot_only:
            print(f"\n[{idx}/{len(runs)}] Plotting reference times for Run {run}...")
            if plot_reference_times(run, out_dir):
                completed_runs.append(run)
            else:
                failed_runs.append((run, "plot_failed"))
            continue

        cmd = [script_path, str(run), str(args.events), str(args.jobs), out_dir]
        cmd_str = " ".join(cmd)

        print(f"\n[{idx}/{len(runs)}] Executing: {cmd_str}")

        if args.dry_run:
            continue

        try:
            subprocess.run(cmd, check=True)
            completed_runs.append(run)
            # Generate reference times plot automatically after run completion
            plot_reference_times(run, out_dir)
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Run {run} failed with exit code {e.returncode}")
            failed_runs.append((run, e.returncode))
        except KeyboardInterrupt:
            print("\nExecution interrupted by user.")
            break

    print("\n" + "=" * 60)
    print(f"Category {category} Execution Summary:")
    print(f"  Total target runs: {len(runs)}")
    print(f"  Completed successfully: {len(completed_runs)}")
    print(f"  Failed runs: {len(failed_runs)}")
    if failed_runs:
        print(f"  Failed run list: {failed_runs}")
    print("=" * 60)


if __name__ == "__main__":
    main()
