#!/bin/bash
# ==============================================================================
# Submit Category III (2023) Partition Jobs for cscint Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catIII_2023_max20.txt"
TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Category III 2023 Partition Jobs for cscint (Max 20 part/run)"
echo " Total jobs: ${TOTAL_JOBS}"
echo " Flavour:    workday"
echo "======================================================================"

condor_submit cscint.sub \
    args_file="${ARGS_FILE}" \
    flavour="workday" \
    "$@"
