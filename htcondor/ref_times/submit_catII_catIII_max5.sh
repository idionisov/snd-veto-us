#!/bin/bash
# ==============================================================================
# Submit Both Category II and Category III Runs (5 Partitions/Run, 364 jobs)
#
# Usage:
#   ./submit_catII_catIII_max5.sh
#   ./submit_catII_catIII_max5.sh force=1   # Force re-running existing partitions
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catII_catIII_max5.txt"
if [ ! -f "${ARGS_FILE}" ]; then
    echo "[ERROR] ${ARGS_FILE} not found! Regenerating..."
    cat "${DIR}/args_partitions_catII_max5.txt" "${DIR}/args_partitions_catIII_max5.txt" > "${ARGS_FILE}"
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Category II & Category III Partition Jobs (5 Partitions/Run)"
echo " Total jobs: ${TOTAL_JOBS} (164 Cat II + 200 Cat III)"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit ref_times.sub \
    args_file="${ARGS_FILE}" \
    flavour="longlunch" \
    "$@"
