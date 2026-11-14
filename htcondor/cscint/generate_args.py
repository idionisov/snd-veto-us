#!/usr/bin/env python3
"""
generate_args.py
----------------
Generates HTCondor arguments for SiPM reference time difference (cscint) extraction per partition.
Filters 2022 runs (Category I & II, >3M entries, nonzero luminosity, is_physics_collision == True)
and scans existing raw partition files on EOS, or filters fast from existing full argument files.

Supports limiting partitions per run via -p / --max-partitions (e.g. -p 15).

Outputs:
  - args_partitions_all[_max<P>].txt
  - args_partitions_catI[_max<P>].txt
  - args_partitions_catII[_max<P>].txt

Format per line:
  <RUN> <PARTITION> <CATEGORY>
"""

import os
import re
import glob
import argparse
from collections import defaultdict
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(REPO_ROOT, "runs_2022.csv")
DATA_DIR = "/eos/experiment/sndlhc/convertedData/physics/2022"
PART_PATTERN = re.compile(r"sndsw_raw-(\d+)\.root")


def norm_cat(c):
    c_str = str(c).strip().upper()
    if c_str in ("I", "CATI"):
        return "catI"
    if c_str in ("II", "CATII"):
        return "catII"
    return None


def scan_partitions(run_dir: str):
    """Scans partition numbers for a run directory."""
    if not run_dir or not os.path.exists(run_dir):
        return []
    raw_files = glob.glob(os.path.join(run_dir, "sndsw_raw-*.root"))
    partitions = []
    for fpath in raw_files:
        m = PART_PATTERN.search(os.path.basename(fpath))
        if m:
            partitions.append(int(m.group(1)))
    partitions.sort()
    return partitions


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTCondor partition argument files for cscint (SiPM Ref Diff) extraction."
    )
    parser.add_argument(
        "--repo-root",
        type=str,
        default=REPO_ROOT,
        help=f"Root of repo containing runs_2022.csv (default: {REPO_ROOT})"
    )
    parser.add_argument(
        "-p", "--max-partitions",
        type=int,
        default=None,
        help="Maximum number of partitions per run (default: None, all partitions)"
    )
    parser.add_argument(
        "-c", "--category",
        type=str,
        default="all",
        choices=["all", "catI", "catII"],
        help="Category to process (default: all)"
    )
    parser.add_argument(
        "--from-existing",
        action="store_true",
        help="Fast mode: filter from existing full args_partitions_*.txt files instead of rescanning EOS"
    )
    parser.add_argument(
        "--suffix",
        type=str,
        default=None,
        help="Suffix for output argument files (default: '' if no partition limit, else '_max<P>')"
    )
    args = parser.parse_args()

    suffix = args.suffix if args.suffix is not None else (f"_max{args.max_partitions}" if args.max_partitions is not None else "")

    catI_jobs = []
    catII_jobs = []

    if args.from_existing:
        print("[INFO] Fast mode: reading from existing full partition args files...")

        def filter_file(fpath):
            if not os.path.exists(fpath):
                return []
            run_map = defaultdict(list)
            with open(fpath) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) >= 3:
                        run_map[parts[0]].append(line)
            out_lines = []
            for r in sorted(run_map.keys(), key=lambda x: int(x)):
                lines = run_map[r]
                if args.max_partitions is not None:
                    lines = lines[:args.max_partitions]
                out_lines.extend(lines)
            return out_lines

        if args.category in ("all", "catI"):
            catI_jobs = filter_file(os.path.join(BASE_DIR, "args_partitions_catI.txt"))
        if args.category in ("all", "catII"):
            catII_jobs = filter_file(os.path.join(BASE_DIR, "args_partitions_catII.txt"))

    else:
        csv_file = os.path.join(args.repo_root, "runs_2022.csv")
        if not os.path.exists(csv_file):
            raise FileNotFoundError(f"Runs catalog not found: {csv_file}")

        df = pd.read_csv(csv_file)
        df["cat_norm"] = df["category"].apply(norm_cat)

        allowed_cats = ["catI", "catII"] if args.category == "all" else [args.category]
        mask = (
            df["cat_norm"].isin(allowed_cats) &
            (df["entries"] > 3000000) &
            (df["luminosity_pb"] > 0) &
            (df["is_physics_collision"] == True)
        )
        qualifying = df[mask].sort_values("run_number")
        print(f"Loaded {len(qualifying)} qualifying runs from {csv_file}.")

        for _, row in qualifying.iterrows():
            run = int(row["run_number"])
            cat = row["cat_norm"]
            run_dir = os.path.join(DATA_DIR, f"run_{run:06d}")

            partitions = scan_partitions(run_dir)
            if not partitions:
                print(f"[WARNING] No raw files found in {run_dir}")
                continue

            if args.max_partitions is not None:
                partitions = partitions[:args.max_partitions]

            for p in partitions:
                line = f"{run} {p} {cat}\n"
                if cat == "catI":
                    catI_jobs.append(line)
                elif cat == "catII":
                    catII_jobs.append(line)

    all_jobs = catI_jobs + catII_jobs

    written_files = []
    if args.category == "all":
        path_all = os.path.join(BASE_DIR, f"args_partitions_all{suffix}.txt")
        with open(path_all, "w") as f:
            f.writelines(all_jobs)
        written_files.append(("All categories", path_all, len(all_jobs)))

    if args.category in ("all", "catI"):
        path_catI = os.path.join(BASE_DIR, f"args_partitions_catI{suffix}.txt")
        with open(path_catI, "w") as f:
            f.writelines(catI_jobs)
        written_files.append(("Category I (2022)", path_catI, len(catI_jobs)))

    if args.category in ("all", "catII"):
        path_catII = os.path.join(BASE_DIR, f"args_partitions_catII{suffix}.txt")
        with open(path_catII, "w") as f:
            f.writelines(catII_jobs)
        written_files.append(("Category II (2022)", path_catII, len(catII_jobs)))

    print("======================================================================")
    print(" HTCondor Partition Job Lists Generated:")
    for desc, pth, count in written_files:
        print(f" {desc:<25}: {count:,} jobs -> {os.path.basename(pth)}")
    print("======================================================================")


if __name__ == "__main__":
    main()
