#!/usr/bin/env python3
"""
merge_ref_times.py
------------------
Merges partition-level reference time histograms into the unified reference time ROOT file:
  /eos/user/i/idioniso/Timing/reference_times_2022.root
organized as:
  <catI | catII>/runXXXX/
    ├── reft-DS
    └── reft-SF

Usage:
  ./merge_ref_times.py [-c catI|catII|all] [-o /path/to/reference_times_2022.root] [-j 4]
"""

import os
import sys
import glob
import re
import argparse
from concurrent.futures import ProcessPoolExecutor
import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.PyConfig.IgnoreCommandLineOptions = True

DEFAULT_INPUT_DIR = "/eos/user/i/idioniso/Timing/ref_times_parts"
DEFAULT_OUTPUT_FILE = "/eos/user/i/idioniso/Timing/reference_times_2022.root"

def parse_args():
    parser = argparse.ArgumentParser(description="Merge partition ROOT files into run-level reference times.")
    parser.add_argument(
        "-i", "--input-dir",
        dest="input_dir",
        default=DEFAULT_INPUT_DIR,
        help=f"Base input directory containing partition files (default: {DEFAULT_INPUT_DIR})"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        default=DEFAULT_OUTPUT_FILE,
        help=f"Target merged ROOT file (default: {DEFAULT_OUTPUT_FILE})"
    )
    parser.add_argument(
        "-c", "--category",
        dest="category",
        default="all",
        choices=["catI", "catII", "all"],
        help="Category to merge (catI, catII, or all; default: all)"
    )
    parser.add_argument(
        "-r", "--run",
        dest="run",
        type=int,
        default=None,
        help="Merge only a specific run number (optional)"
    )
    parser.add_argument(
        "-f", "--force",
        dest="force",
        action="store_true",
        default=False,
        help="Overwrite existing runs in target file"
    )
    return parser.parse_args()


def merge_run(run_dir, cat, run_nr):
    """Sums all partition histograms for a given run and returns merged TH1Fs."""
    part_files = sorted(glob.glob(os.path.join(run_dir, "part_*.root")))
    if not part_files:
        return None

    h_ds_total = None
    h_sf_total = None

    for pf in part_files:
        f = ROOT.TFile.Open(pf, "READ")
        if not f or f.IsZombie():
            continue

        h_ds = f.Get("reft-DS")
        h_sf = f.Get("reft-SF")

        if h_ds:
            if h_ds_total is None:
                h_ds_total = h_ds.Clone(f"reft-DS_run{run_nr}")
                h_ds_total.SetDirectory(0)
            else:
                h_ds_total.Add(h_ds)

        if h_sf:
            if h_sf_total is None:
                h_sf_total = h_sf.Clone(f"reft-SF_run{run_nr}")
                h_sf_total.SetDirectory(0)
            else:
                h_sf_total.Add(h_sf)

        f.Close()

    return {
        "cat": cat,
        "run": run_nr,
        "n_parts": len(part_files),
        "h_ds": h_ds_total,
        "h_sf": h_sf_total
    }


def main():
    args = parse_args()
    input_dir = args.input_dir
    output_file = args.output_file

    if not os.path.exists(input_dir):
        print(f"[ERROR] Input directory does not exist: {input_dir}", file=sys.stderr)
        sys.exit(1)

    categories = ["catI", "catII"] if args.category == "all" else [args.category]

    print("======================================================================")
    print(" SND@LHC Reference Time Partition Merger")
    print(f" Input Directory  : {input_dir}")
    print(f" Output Target    : {output_file}")
    print(f" Categories       : {', '.join(categories)}")
    print("======================================================================")

    # Gather all available run directories
    runs_to_process = []
    run_dir_pattern = re.compile(r"run(\d+)")

    for cat in categories:
        cat_dir = os.path.join(input_dir, cat)
        if not os.path.exists(cat_dir):
            continue

        for r_entry in os.listdir(cat_dir):
            m = run_dir_pattern.match(r_entry)
            if not m:
                continue
            r_nr = int(m.group(1))
            if args.run is not None and r_nr != args.run:
                continue

            full_rdir = os.path.join(cat_dir, r_entry)
            if os.path.isdir(full_rdir):
                runs_to_process.append((cat, r_nr, full_rdir))

    runs_to_process.sort(key=lambda x: (x[0], x[1]))
    print(f"Found {len(runs_to_process)} runs with partition data to merge.")

    if not runs_to_process:
        print("[INFO] No partition runs found to merge.")
        return

    # Check target file and open with UPDATE mode
    out_dir = os.path.dirname(os.path.abspath(output_file))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    target_file = ROOT.TFile.Open(output_file, "UPDATE")
    if not target_file or target_file.IsZombie():
        print(f"[ERROR] Could not open target file {output_file} for writing!", file=sys.stderr)
        sys.exit(1)

    merged_count = 0
    total_ds_entries = 0
    total_sf_entries = 0

    for cat, r_nr, r_dir in runs_to_process:
        cat_t_dir = target_file.GetDirectory(cat)
        if not cat_t_dir:
            cat_t_dir = target_file.mkdir(cat)

        run_sub_dir_name = f"run{r_nr}"
        existing_run_dir = cat_t_dir.GetDirectory(run_sub_dir_name)
        if existing_run_dir and not args.force:
            print(f" ~ [{cat}] Run {r_nr} already present in {output_file}. Use --force to replace.")
            continue

        res = merge_run(r_dir, cat, r_nr)
        if not res or (not res["h_ds"] and not res["h_sf"]):
            continue

        if not existing_run_dir:
            run_t_dir = cat_t_dir.mkdir(run_sub_dir_name)
        else:
            run_t_dir = existing_run_dir

        run_t_dir.cd()
        ds_entries = 0
        sf_entries = 0

        if res["h_ds"]:
            res["h_ds"].Write("reft-DS", ROOT.TObject.kOverwrite)
            ds_entries = res["h_ds"].GetEntries()
            total_ds_entries += ds_entries

        if res["h_sf"]:
            res["h_sf"].Write("reft-SF", ROOT.TObject.kOverwrite)
            sf_entries = res["h_sf"].GetEntries()
            total_sf_entries += sf_entries

        print(f" [{cat}] Merged Run {r_nr} ({res['n_parts']} parts) -> reft-DS: {ds_entries:,.0f}, reft-SF: {sf_entries:,.0f}")
        merged_count += 1

    target_file.Close()

    print("======================================================================")
    print(f"[SUCCESS] Merging complete. Updated {merged_count} runs in {output_file}.")
    print(f" Total DS reference entries: {total_ds_entries:,.0f}")
    print(f" Total SF reference entries: {total_sf_entries:,.0f}")
    print("======================================================================")


if __name__ == "__main__":
    main()
