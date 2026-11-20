#!/bin/bash
# ==============================================================================
# Submit 10 Qualifying 2026 Category III Runs (10 Partitions/Run, 100 jobs total)
# Flavour: workday (longer duration to prevent timeouts)
#
# Runs: 13085, 13098, 13101, 13104, 13162, 13406, 13480, 13503, 13508, 13520
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catIII_2026_max10.txt"
if [ ! -f "${ARGS_FILE}" ]; then
    echo "[ERROR] ${ARGS_FILE} not found!" >&2
    exit 1
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")
FLAVOUR="${1:-workday}"

echo "======================================================================"
echo " Submitting 10 Top 2026 Category III Runs (10 Partitions/Run)"
echo " Total jobs: ${TOTAL_JOBS}"
echo " Arguments:  ${ARGS_FILE}"
echo " Flavour:    ${FLAVOUR}"
echo " Force:      1"
echo "======================================================================"

condor_submit ref_times_2026.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="1"
