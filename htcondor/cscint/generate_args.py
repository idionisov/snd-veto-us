#!/usr/bin/env python3
"""
generate_args.py
----------------
Generates HTCondor arguments for reference time extraction per partition.
Filters 2022 runs (Category I & II, >3M entries, nonzero luminosity, is_physics_collision == True)
and scans existing raw partition files on EOS.

Outputs:
  - args_partitions_all.txt
  - args_partitions_catI.txt
  - args_partitions_catII.txt

Format per line:
  <RUN> <PARTITION> <CATEGORY>
"""

import os
import re
import glob
import pandas as pd

CSV_PATH = "/afs/cern.ch/work/i/idioniso/snd-veto-us/runs_2022.csv"
DATA_DIR = "/eos/experiment/sndlhc/convertedData/physics/2022"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def norm_cat(c):
    c_str = str(c).strip().upper()
    if c_str in ("I", "CATI"):
        return "catI"
    if c_str in ("II", "CATII"):
        return "catII"
    return None

def main():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"Runs catalog not found: {CSV_PATH}")

    df = pd.read_csv(CSV_PATH)
    df["cat_norm"] = df["category"].apply(norm_cat)

    mask = (
        df["cat_norm"].isin(["catI", "catII"]) &
        (df["entries"] > 3000000) &
        (df["luminosity_pb"] > 0) &
        (df["is_physics_collision"] == True)
    )
    qualifying = df[mask].sort_values("run_number")

    print(f"Loaded {len(qualifying)} qualifying runs from {CSV_PATH}.")

    all_jobs = []
    catI_jobs = []
    catII_jobs = []

    part_pattern = re.compile(r"sndsw_raw-(\d+)\.root")

    for _, row in qualifying.iterrows():
        run = int(row["run_number"])
        cat = row["cat_norm"]
        run_dir = os.path.join(DATA_DIR, f"run_{run:06d}")

        if not os.path.exists(run_dir):
            print(f"[WARNING] Directory not found for run {run}: {run_dir}")
            continue

        raw_files = glob.glob(os.path.join(run_dir, "sndsw_raw-*.root"))
        partitions = []
        for fpath in raw_files:
            fname = os.path.basename(fpath)
            m = part_pattern.search(fname)
            if m:
                partitions.append(int(m.group(1)))

        partitions.sort()
        if not partitions:
            print(f"[WARNING] No raw files found in {run_dir}")
            continue

        for p in partitions:
            line = f"{run} {p} {cat}\n"
            all_jobs.append(line)
            if cat == "catI":
                catI_jobs.append(line)
            elif cat == "catII":
                catII_jobs.append(line)

    # Write output files
    path_all = os.path.join(BASE_DIR, "args_partitions_all.txt")
    path_catI = os.path.join(BASE_DIR, "args_partitions_catI.txt")
    path_catII = os.path.join(BASE_DIR, "args_partitions_catII.txt")

    with open(path_all, "w") as f:
        f.writelines(all_jobs)
    with open(path_catI, "w") as f:
        f.writelines(catI_jobs)
    with open(path_catII, "w") as f:
        f.writelines(catII_jobs)

    print("======================================================================")
    print(" HTCondor Partition Job Lists Generated:")
    print(f" Total partition jobs (All)   : {len(all_jobs):,} -> {path_all}")
    print(f" Category I partition jobs     : {len(catI_jobs):,} -> {path_catI}")
    print(f" Category II partition jobs    : {len(catII_jobs):,} -> {path_catII}")
    print("======================================================================")

if __name__ == "__main__":
    main()
