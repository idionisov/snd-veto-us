#!/bin/bash
# ==============================================================================
# Submit Category III 2023 Partition Jobs for Reference Time Extraction
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting Category III 2023 Partition Jobs (10 runs)"
echo " Total jobs: $(wc -l < args_partitions_catIII_2023.txt)"
echo " Flavour:    longlunch"
echo "======================================================================"

condor_submit ref_times_2023.sub "$@"
