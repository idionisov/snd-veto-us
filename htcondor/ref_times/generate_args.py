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
    parser.add_argument(
        "-p", "--max-partitions",
        type=int,
        default=None,
        help="Maximum number of partitions per run (default: None, all partitions)"
    )
    parser.add_argument(
        "-t", "--top-runs",
        type=int,
        default=10,
        help="Number of highest-entries collision runs to select per year for Cat III (default: 10)"
    )
    parser.add_argument(
        "-c", "--category",
        type=str,
        default="all",
        choices=["all", "catI", "catII", "catIII"],
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
    catIII_jobs_by_year = {y: [] for y in (2023, 2024, 2025, 2026)}
    catIII_jobs = []

    if args.from_existing:
        print("[INFO] Fast mode: reading from existing full partition args files...")
        from collections import defaultdict

        def filter_file(fpath):
            if not os.path.exists(fpath):
                return []
            run_map = defaultdict(list)
            with open(fpath) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        run_map[parts[0]].append(line)
            out = []
            for r, lines in run_map.items():
                if args.max_partitions is not None:
                    out.extend(lines[:args.max_partitions])
                else:
                    out.extend(lines)
            return out

        if args.category in ("all", "catI"):
            catI_jobs = filter_file(os.path.join(BASE_DIR, "args_partitions_catI.txt"))
        if args.category in ("all", "catII"):
            catII_jobs = filter_file(os.path.join(BASE_DIR, "args_partitions_catII.txt"))
        if args.category in ("all", "catIII"):
            for y in (2023, 2024, 2025, 2026):
                src_y = os.path.join(BASE_DIR, f"args_partitions_catIII_{y}.txt")
                catIII_jobs_by_year[y] = filter_file(src_y)
                catIII_jobs.extend(catIII_jobs_by_year[y])
    else:
        # 1. Process 2022 (Category I & Category II)
        if args.category in ("all", "catI", "catII"):
            csv_2022 = os.path.join(args.repo_root, "runs_2022.csv")
            if os.path.exists(csv_2022):
                df_2022 = pd.read_csv(csv_2022)
                df_2022["cat_norm"] = df_2022["category"].apply(norm_cat)
                allowed_cats = ["catI", "catII"] if args.category == "all" else [args.category]
                mask_2022 = (
                    df_2022["cat_norm"].isin(allowed_cats) &
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
                    if args.max_partitions is not None:
                        partitions = partitions[:args.max_partitions]
                    for p in partitions:
                        line = f"{run} {p} {cat}\n"
                        if cat == "catI":
                            catI_jobs.append(line)
                        elif cat == "catII":
                            catII_jobs.append(line)

        # 2. Process 2023-2026 (Category III: top runs with the most entries per year)
        if args.category in ("all", "catIII"):
            for y in (2023, 2024, 2025, 2026):
                csv_y = os.path.join(args.repo_root, f"runs_{y}.csv")
                if not os.path.exists(csv_y):
                    print(f"[WARNING] Catalog not found: {csv_y}")
                    continue
                df_y = pd.read_csv(csv_y)
                mask_y = (
                    (df_y["is_physics_collision"] == True) &
                    (df_y["luminosity_pb"] > 0)
                )
                qual_y = (
                    df_y[mask_y]
                    .sort_values("entries", ascending=False)
                    .head(args.top_runs)
                    .sort_values("run_number")
                )
                print(f"Year {y}: Loaded {len(qual_y)} qualifying Category III runs (top {args.top_runs} by entries).")

                for _, row in qual_y.iterrows():
                    run = int(row["run_number"])
                    run_dir = get_run_dir(y, run)
                    partitions = scan_partitions(run_dir)
                    if not partitions:
                        print(f"[WARNING] No raw files found in {run_dir}")
                        continue
                    if args.max_partitions is not None:
                        partitions = partitions[:args.max_partitions]
                    for p in partitions:
                        line = f"{run} {p} catIII\n"
                        catIII_jobs_by_year[y].append(line)
                        catIII_jobs.append(line)

    all_jobs = catI_jobs + catII_jobs + catIII_jobs

    # 3. Write argument files
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

    if args.category in ("all", "catIII"):
        path_catIII = os.path.join(BASE_DIR, f"args_partitions_catIII{suffix}.txt")
        with open(path_catIII, "w") as f:
            f.writelines(catIII_jobs)
        written_files.append(("Category III (all)", path_catIII, len(catIII_jobs)))

        for y in (2023, 2024, 2025, 2026):
            path_y = os.path.join(BASE_DIR, f"args_partitions_catIII_{y}{suffix}.txt")
            with open(path_y, "w") as f:
                f.writelines(catIII_jobs_by_year[y])
            written_files.append((f"  Category III ({y})", path_y, len(catIII_jobs_by_year[y])))

    print("======================================================================")
    print(" HTCondor Partition Job Lists Generated:")
    for desc, pth, count in written_files:
        print(f" {desc:<25}: {count:,} jobs -> {os.path.basename(pth)}")
    print("======================================================================")


if __name__ == "__main__":
    main()
