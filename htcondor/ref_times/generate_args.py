#!/usr/bin/env python3
"""
generate_args.py
----------------
Generates HTCondor arguments for reference time extraction per partition.
Filters runs by Category:
  - Category I & II (2022): >3M entries, nonzero luminosity, is_physics_collision == True
  - Category III (2023-2026): 10 runs with the most entries per year, nonzero luminosity, is_physics_collision == True

Outputs:
  - args_partitions_all.txt          (All categories: Cat I + Cat II + Cat III)
  - args_partitions_catI.txt         (2022 Category I)
  - args_partitions_catII.txt        (2022 Category II)
  - args_partitions_catIII.txt       (2023-2026 Category III, all 40 runs)
  - args_partitions_catIII_2023.txt  (2023 Category III, top 10 runs)
  - args_partitions_catIII_2024.txt  (2024 Category III, top 10 runs)
  - args_partitions_catIII_2025.txt  (2025 Category III, top 10 runs)
  - args_partitions_catIII_2026.txt  (2026 Category III, top 10 runs)

Format per line:
  <RUN> <PARTITION> <CATEGORY>
"""

import os
import re
import glob
import argparse
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

THRESHOLDS_CATIII = {
    2023: 227000000,
    2024: 535900000,
    2025: 361000000,
    2026: 357000000,
}

PART_PATTERN = re.compile(r"sndsw_raw-(\d+)\.root")


def norm_cat(c):
    c_str = str(c).strip().upper()
    if c_str in ("I", "CATI"):
        return "catI"
    if c_str in ("II", "CATII"):
        return "catII"
    if c_str in ("III", "CATIII"):
        return "catIII"
    return None


def get_run_dir(year: int, run: int) -> str:
    """Resolves directory path on EOS for a given run and year."""
    if year == 2022:
        return f"/eos/experiment/sndlhc/convertedData/physics/2022/run_{run:06d}"
    elif year == 2023:
        return f"/eos/experiment/sndlhc/convertedData/physics/2023/run_{run:06d}"
    elif year == 2024:
        sub = glob.glob(f"/eos/experiment/sndlhc/convertedData/physics/2024/run_24*/run_{run:06d}")
        return sub[0] if sub else ""
    elif year in (2025, 2026):
        sub = glob.glob(f"/eos/experiment/sndlhc/convertedData/physics/{year}/run_2*/run_{run:06d}")
        return sub[0] if sub else ""
    return ""


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
    parser = argparse.ArgumentParser(description="Generate HTCondor partition argument files for reference times.")
    parser.add_argument(
        "--repo-root",
        type=str,
        default=REPO_ROOT,
        help=f"Root of sndVetoUS repo containing runs_YYYY.csv (default: {REPO_ROOT})"
    )
    args = parser.parse_args()

    catI_jobs = []
    catII_jobs = []
    catIII_jobs_by_year = {y: [] for y in (2023, 2024, 2025, 2026)}
    catIII_jobs = []

    # 1. Process 2022 (Category I & Category II)
    csv_2022 = os.path.join(args.repo_root, "runs_2022.csv")
    if os.path.exists(csv_2022):
        df_2022 = pd.read_csv(csv_2022)
        df_2022["cat_norm"] = df_2022["category"].apply(norm_cat)
        mask_2022 = (
            df_2022["cat_norm"].isin(["catI", "catII"]) &
            (df_2022["entries"] > 3000000) &
            (df_2022["luminosity_pb"] > 0) &
            (df_2022["is_physics_collision"] == True)
        )
        qual_2022 = df_2022[mask_2022].sort_values("run_number")
        print(f"Loaded {len(qual_2022)} qualifying 2022 runs (>3M entries, nonzero lumi).")

        for _, row in qual_2022.iterrows():
            run = int(row["run_number"])
            cat = row["cat_norm"]
            run_dir = get_run_dir(2022, run)
            partitions = scan_partitions(run_dir)
            if not partitions:
                print(f"[WARNING] No raw files found in {run_dir}")
                continue
            for p in partitions:
                line = f"{run} {p} {cat}\n"
                if cat == "catI":
                    catI_jobs.append(line)
                elif cat == "catII":
                    catII_jobs.append(line)

    # 2. Process 2023-2026 (Category III: 10 runs with the most entries per year)
    for y in (2023, 2024, 2025, 2026):
        csv_y = os.path.join(args.repo_root, f"runs_{y}.csv")
        if not os.path.exists(csv_y):
            print(f"[WARNING] Catalog not found: {csv_y}")
            continue
        df_y = pd.read_csv(csv_y)
        thresh = THRESHOLDS_CATIII[y]
        mask_y = (
            (df_y["is_physics_collision"] == True) &
            (df_y["luminosity_pb"] > 0) &
            (df_y["entries"] > thresh)
        )
        qual_y = df_y[mask_y].sort_values("run_number")
        print(f"Year {y}: Loaded {len(qual_y)} qualifying Category III runs (entries > {thresh:,}).")

        for _, row in qual_y.iterrows():
            run = int(row["run_number"])
            run_dir = get_run_dir(y, run)
            partitions = scan_partitions(run_dir)
            if not partitions:
                print(f"[WARNING] No raw files found in {run_dir}")
                continue
            for p in partitions:
                line = f"{run} {p} catIII\n"
                catIII_jobs_by_year[y].append(line)
                catIII_jobs.append(line)

    all_jobs = catI_jobs + catII_jobs + catIII_jobs

    # 3. Write argument files
    path_all = os.path.join(BASE_DIR, "args_partitions_all.txt")
    path_catI = os.path.join(BASE_DIR, "args_partitions_catI.txt")
    path_catII = os.path.join(BASE_DIR, "args_partitions_catII.txt")
    path_catIII = os.path.join(BASE_DIR, "args_partitions_catIII.txt")

    with open(path_all, "w") as f:
        f.writelines(all_jobs)
    with open(path_catI, "w") as f:
        f.writelines(catI_jobs)
    with open(path_catII, "w") as f:
        f.writelines(catII_jobs)
    with open(path_catIII, "w") as f:
        f.writelines(catIII_jobs)

    for y in (2023, 2024, 2025, 2026):
        path_y = os.path.join(BASE_DIR, f"args_partitions_catIII_{y}.txt")
        with open(path_y, "w") as f:
            f.writelines(catIII_jobs_by_year[y])

    print("======================================================================")
    print(" HTCondor Partition Job Lists Generated:")
    print(f" Total partition jobs (All)      : {len(all_jobs):,} -> {path_all}")
    print(f" Category I partition jobs (2022) : {len(catI_jobs):,} -> {path_catI}")
    print(f" Category II partition jobs (2022): {len(catII_jobs):,} -> {path_catII}")
    print(f" Category III partition jobs     : {len(catIII_jobs):,} -> {path_catIII}")
    for y in (2023, 2024, 2025, 2026):
        print(f"   - {y} Category III (10 runs) : {len(catIII_jobs_by_year[y]):,} -> args_partitions_catIII_{y}.txt")
    print("======================================================================")


if __name__ == "__main__":
    main()
