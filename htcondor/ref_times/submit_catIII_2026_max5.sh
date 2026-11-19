#!/bin/bash
# ==============================================================================
# Submit 10 Qualifying 2026 Category III Runs (5 Partitions/Run, 50 jobs total)
#
# Runs: 13520, 13503, 13162, 13480, 13104, 13101, 13085, 13406, 13508, 13098
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catIII_2026_max5.txt"
if [ ! -f "${ARGS_FILE}" ]; then
    echo "[ERROR] ${ARGS_FILE} not found! Run generate_args.py -p 5 first." >&2
    exit 1
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting 10 Top 2026 Category III Runs (5 Partitions/Run)"
echo " Total jobs: ${TOTAL_JOBS}"
echo " Arguments:  ${ARGS_FILE}"
echo " Flavour:    longlunch"
echo " Force:      1 (reprocess with updated ref_times.py without veto/scifi1 cut)"
echo "======================================================================"

condor_submit ref_times_2026.sub \
    args_file="${ARGS_FILE}" \
    flavour="longlunch" \
    force="1" \
    "$@"
