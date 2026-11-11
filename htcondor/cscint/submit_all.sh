#!/bin/bash
# ==============================================================================
# Submit All 2022 Partition Jobs for cscint (SiPM Ref Diff) Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting ALL Partition Jobs for cscint (Cat I + Cat II)"
echo " Total jobs: $(wc -l < args_partitions_all.txt)"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit cscint.sub \
    args_file="${DIR}/args_partitions_all.txt" \
    flavour="longlunch" \
    "$@"
