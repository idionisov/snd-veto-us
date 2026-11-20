#!/bin/bash
# ==============================================================================
# Submit Category III (2025) Partition Jobs for Inter-System Shift Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting Category III 2025 Partition Jobs (Inter-System Shift)"
echo " Total jobs: $(wc -l < args_partitions_catIII_2025_max20.txt)"
echo " Flavour:    workday"
echo "======================================================================"

condor_submit interSystemShift.sub \
    args_file="${DIR}/args_partitions_catIII_2025_max20.txt" \
    flavour="workday" \
    "$@"
