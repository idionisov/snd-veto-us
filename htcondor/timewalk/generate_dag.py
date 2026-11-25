#!/usr/bin/env python3
"""
generate_dag.py
---------------
Generates HTCondor DAGMan workflows that chain:
  [1] Filling partition histograms  (fill_<RUN>)
  [2] Merging partitions into run    (merge_<RUN>)
  [3] Fitting time-walk calibration  (fit_<RUN>)

Each run executes independently in parallel. As soon as all partitions
for run R finish, merge_R and fit_R proceed immediately without waiting
for other runs.
"""

import os
import sys
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DAG_ARGS_DIR = os.path.join(BASE_DIR, "dag_args")
os.makedirs(DAG_ARGS_DIR, exist_ok=True)

GROUPS = {
    "catII_2022": {
        "label": "Cat II (2022)",
        "source_args": "args_partitions_catII_max50.txt",
        "dag_file": "timewalk_catII_2022.dag",
    },
    "catIII_2023": {
        "label": "Cat III (2023)",
        "source_args": "args_partitions_catIII_2023_max50.txt",
        "dag_file": "timewalk_catIII_2023.dag",
    },
    "catIII_2024": {
        "label": "Cat III (2024)",
        "source_args": "args_partitions_catIII_2024_max50.txt",
        "dag_file": "timewalk_catIII_2024.dag",
    },
    "catIII_2025": {
        "label": "Cat III (2025)",
        "source_args": "args_partitions_catIII_2025_max50.txt",
        "dag_file": "timewalk_catIII_2025.dag",
    },
    "catIII_2026": {
        "label": "Cat III (2026)",
        "source_args": "args_partitions_catIII_2026_max50.txt",
        "dag_file": "timewalk_catIII_2026.dag",
    },
}


def build_dag_content(runs_dict, group_name=""):
    """
    Builds DAGMan text content for given dictionary:
    { run_num: (category, [line1, line2, ...]) }
    """
    lines = [
        f"# ==============================================================================",
        f"# HTCondor DAGMan Workflow: Time-Walk Calibration Pipeline",
        f"# Group: {group_name}",
        f"# Runs : {len(runs_dict)} independent run pipelines (Fill -> Merge -> Fit)",
        f"# ==============================================================================",
        "",
        "CONFIG dagman.config",
        "",
    ]

    # Job Definitions
    for run in sorted(runs_dict.keys()):
        cat, part_lines = runs_dict[run]
        parts_file = os.path.join(DAG_ARGS_DIR, f"parts_run{run}.txt")

        # Write per-run partition args file
        with open(parts_file, "w") as pf:
            pf.write("\n".join(part_lines) + "\n")

        lines.append(f"# --- Run {run} ({cat}, {len(part_lines)} partitions) ---")
        lines.append(f"JOB  fill_{run}   timewalk.sub")
        lines.append(f'VARS fill_{run}   args_file="{parts_file}"')
        lines.append(f"RETRY fill_{run}  2")
        lines.append("")
        lines.append(f"JOB  merge_{run}  merge_single_run.sub")
        lines.append(f'VARS merge_{run}  run="{run}" category="{cat}"')
        lines.append(f"RETRY merge_{run} 2")
        lines.append("")
        lines.append(f"JOB  fit_{run}    fit_single_run.sub")
        lines.append(f'VARS fit_{run}    run="{run}"')
        lines.append(f"RETRY fit_{run}   2")
        lines.append("")
        lines.append(f"PARENT fill_{run} CHILD merge_{run}")
        lines.append(f"PARENT merge_{run} CHILD fit_{run}")
        lines.append("")

    return "\n".join(lines)


def main():
    print(f"Generating HTCondor DAGMan pipelines in: {BASE_DIR}")
    
    # 1. Write dagman.config
    cfg_file = os.path.join(BASE_DIR, "dagman.config")
    with open(cfg_file, "w") as f:
        f.write("# DAGMan configuration\n")
        f.write("DAGMAN_MAX_JOBS_SUBMITTED = 1000\n")
        f.write("DAGMAN_MAX_SUBMITS_PER_INTERVAL = 50\n")
        f.write("DAGMAN_USER_LOG_SCAN_INTERVAL = 5\n")
    print(f"  -> Created {cfg_file}")

    all_runs = {}

    for group_key, info in GROUPS.items():
        src_path = os.path.join(BASE_DIR, info["source_args"])
        if not os.path.exists(src_path):
            print(f"  [WARN] Source file missing: {src_path}")
            continue

        group_runs = defaultdict(lambda: ("", []))
        with open(src_path, "r") as sf:
            for line in sf:
                line_str = line.strip()
                if not line_str:
                    continue
                parts = line_str.split()
                run_nr = int(parts[0])
                cat = parts[2]
                group_runs[run_nr] = (cat, group_runs[run_nr][1] + [line_str])
                all_runs[run_nr] = (cat, all_runs[run_nr][1] + [line_str] if run_nr in all_runs else [line_str])

        dag_path = os.path.join(BASE_DIR, info["dag_file"])
        content = build_dag_content(group_runs, info["label"])
        with open(dag_path, "w") as df:
            df.write(content)
        
        n_parts = sum(len(p[1]) for p in group_runs.values())
        print(f"  -> Generated {info['dag_file']:25s}: {len(group_runs):2d} runs, {n_parts:5d} partition jobs")

    # Master DAG covering all eras
    all_dag_path = os.path.join(BASE_DIR, "timewalk_all.dag")
    content_all = build_dag_content(all_runs, "All Eras (Cat II 2022 + Cat III 2023-2026)")
    with open(all_dag_path, "w") as df:
        df.write(content_all)
    n_all_parts = sum(len(p[1]) for p in all_runs.values())
    print(f"  -> Generated {'timewalk_all.dag':25s}: {len(all_runs):2d} runs, {n_all_parts:5d} partition jobs")
    print(f"[SUCCESS] DAG definitions generated. Partition args stored in: {DAG_ARGS_DIR}")


if __name__ == "__main__":
    main()
