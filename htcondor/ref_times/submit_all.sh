#!/bin/bash
# ==============================================================================
# Submit All Partition Jobs for Reference Time Extraction (Cat I + Cat II + Cat III)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting ALL Partition Jobs (Cat I + Cat II + Cat III)"
echo " Total jobs: $(wc -l < args_partitions_all.txt)"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit ref_times.sub \
    args_file="${DIR}/args_partitions_all.txt" \
    flavour="longlunch" \
    "$@"
