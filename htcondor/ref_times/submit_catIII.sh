#!/bin/bash
# ==============================================================================
# Submit Category III Partition Jobs for Reference Time Extraction (2023-2026)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting Category III Partition Jobs (2023 - 2026, 40 runs)"
echo " Total jobs: $(wc -l < args_partitions_catIII.txt)"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit ref_times.sub \
    args_file="${DIR}/args_partitions_catIII.txt" \
    flavour="longlunch" \
    "$@"
