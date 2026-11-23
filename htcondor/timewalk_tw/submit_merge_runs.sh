#!/bin/bash
# ==============================================================================
# Submit Run-Level Partition Merging Jobs for Time-Walk Iteration 2
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="${1:-all}"
shift || true

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-1}"

case "${TARGET}" in
    catII|catii|CATII|2022)
        ARGS_FILE="${DIR}/args_merge_runs_catII.txt"
        ;;
    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2023.txt"
        ;;
    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2025.txt"
        ;;
    all|ALL)
        ARGS_FILE="${DIR}/args_merge_runs_all.txt"
        ;;
    *)
        echo "[ERROR] Unknown target: ${TARGET}" >&2
        echo "Valid targets: catII, 2023, 2025, all" >&2
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

if [[ "$*" == *"--dry-run"* ]]; then
    echo "[INFO] Dry run requested. Exiting without submitting."
    exit 0
fi

condor_submit merge_runs.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE_FLAG}" \
    "$@"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_RUNS} merge jobs for target '${TARGET}'."
echo " Monitor with: condor_q or ./status_merge_runs.sh"
echo "======================================================================"
