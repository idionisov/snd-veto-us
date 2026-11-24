#!/bin/bash
# ==============================================================================
# Submit Run-Level Partition Merging Jobs for Time-Walk Iteration 2
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  catII | 2022            Category II (2022)
  2023 | catIII_2023      Category III (2023)
  2024 | catIII_2024      Category III (2024)
  2025 | catIII_2025      Category III (2025)
  2026 | catIII_2026      Category III (2026)
  all                     All available runs

Options:
  --flavour FLAVOUR       HTCondor job flavour (default: workday)
  --dry-run               Display runs without submitting
  -h, --help              Show this help
EOF
    exit 0
}

TARGET="all"
FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-1}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --flavour)
            FLAVOUR="$2"; shift 2 ;;
        catII|catii|CATII|2022|2023|catIII_2023|2024|catIII_2024|2025|catIII_2025|2026|catIII_2026|all|ALL)
            TARGET="$1"; shift ;;
        *)
            echo "[ERROR] Unknown target or option: $1" >&2
            echo "Valid targets: catII, 2023, 2024, 2025, 2026, all" >&2
            exit 1 ;;
    esac
done

case "${TARGET}" in
    catII|catii|CATII|2022)
        ARGS_FILE="${DIR}/args_merge_runs_catII.txt"
        ;;
    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2023.txt"
        ;;
    2024|catIII_2024)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2024.txt"
        ;;
    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2025.txt"
        ;;
    2026|catIII_2026)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2026.txt"
        ;;
    all|ALL)
        ARGS_FILE="${DIR}/args_merge_runs_all.txt"
        ;;
    *)
        echo "[ERROR] Unknown target: ${TARGET}" >&2
        echo "Valid targets: catII, 2023, 2024, 2025, 2026, all" >&2
        exit 1
        ;;
esac

N_RUNS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Run Merge Jobs (Time-Walk Iteration 2)"
echo " Target Category : ${TARGET}"
echo " Total Runs      : ${N_RUNS}"
echo " Job Flavour     : ${FLAVOUR}"
echo " Force Overwrite : FORCE=${FORCE_FLAG}"
echo " Args File       : ${ARGS_FILE}"
echo " Destination     : /eos/user/i/idioniso/Timing/timewalk_tw/runs"
echo " Time            : $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. Exiting without submitting."
    exit 0
fi

condor_submit merge_runs.sub     args_file="${ARGS_FILE}"     flavour="${FLAVOUR}"     force="${FORCE_FLAG}"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_RUNS} merge jobs for target '${TARGET}'."
echo " Monitor with: condor_q or ./status_merge_runs.sh"
echo "======================================================================"
