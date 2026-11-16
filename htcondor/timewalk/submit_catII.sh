#!/bin/bash
# ==============================================================================
# Submit Category II Partition Jobs for Time-Walk Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"

echo "======================================================================"
echo " Submitting Category II Partition Jobs for Time-Walk"
echo " Total jobs: $(wc -l < args_partitions_catII_max20.txt)"
echo " Flavour:    ${FLAVOUR}"
echo " Force:      ${FORCE_FLAG}"
echo "======================================================================"

condor_submit timewalk.sub \
    args_file="${DIR}/args_partitions_catII_max20.txt" \
    flavour="${FLAVOUR}" \
    force="${FORCE_FLAG}" \
    "$@"
