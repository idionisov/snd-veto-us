#!/bin/bash
# ==============================================================================
# Submit Category II Partition Jobs for Reference Time Extraction (Max 5/Run)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catII_max5.txt"
if [ ! -f "${ARGS_FILE}" ]; then
    echo "[ERROR] ${ARGS_FILE} not found! Run generate_args.py -p 5 first." >&2
    exit 1
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Category II Partition Jobs (Max 5 Partitions/Run)"
echo " Total jobs: ${TOTAL_JOBS}"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit ref_times.sub \
    args_file="${ARGS_FILE}" \
    flavour="longlunch" \
    "$@"
