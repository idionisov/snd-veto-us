#!/bin/bash
# ==============================================================================
# Submit Category II Partition Jobs for cscint (SiPM Ref Diff) Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting Category II Partition Jobs for cscint"
echo " Total jobs: $(wc -l < args_partitions_catII.txt)"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit cscint.sub \
    args_file="${DIR}/args_partitions_catII.txt" \
    flavour="longlunch" \
    "$@"
