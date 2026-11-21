#!/bin/bash
# ==============================================================================
# Submit Category III (2025) Partition Jobs for cscint Extraction (Max 15 Partitions/Run)
#
# Configuration:
#   - 10 highest-entry collision runs
#   - Up to 15 partitions per run (max 150 jobs)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catIII_2025_max15.txt"

if [ ! -f "${ARGS_FILE}" ]; then
    echo "[INFO] ${ARGS_FILE} not found. Generating argument list..."
    python3 "${DIR}/generate_args.py" -c catIII -p 15
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Category III 2025 Partition Jobs for cscint (Max 15 part/run)"
echo " Total jobs: ${TOTAL_JOBS} (10 runs x max 15 partitions)"
echo " Flavour:    workday"
echo " Arguments:  ${ARGS_FILE}"
echo "======================================================================"

condor_submit cscint.sub \
    args_file="${ARGS_FILE}" \
    flavour="workday" \
    "$@"
