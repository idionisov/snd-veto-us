#!/bin/bash
# ==============================================================================
# Submit Category II Partition Jobs for Time-Walk Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"

# Prefer max40, fallback to max20
ARGS_FILE="${DIR}/args_partitions_catII_max40.txt"
if [ ! -f "${ARGS_FILE}" ]; then
    ARGS_FILE="${DIR}/args_partitions_catII_max20.txt"
fi

echo "======================================================================"
echo " Submitting Category II Partition Jobs for Time-Walk"
echo " Total jobs: $(wc -l < "${ARGS_FILE}")"
echo " Args File:  ${ARGS_FILE}"
echo " Flavour:    ${FLAVOUR}"
echo " Force:      ${FORCE_FLAG}"
echo "======================================================================"

condor_submit timewalk.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE_FLAG}" \
    "$@"
