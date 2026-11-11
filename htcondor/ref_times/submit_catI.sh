#!/bin/bash
# ==============================================================================
# Submit Category I Partition Jobs for Reference Time Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting Category I Partition Jobs"
echo " Total jobs: $(wc -l < args_partitions_catI.txt)"
echo " Flavour:    workday"
echo "======================================================================"

condor_submit ref_times.sub \
    args_file="${DIR}/args_partitions_catI.txt" \
    flavour="workday" \
    "$@"
