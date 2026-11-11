#!/bin/bash
# ==============================================================================
# Submit Category III Top 10 Runs (Max 15 Partitions/Run, 600 jobs total)
#
# Usage:
#   ./submit_catIII_max15.sh                # Submits 4 clusters of 150 jobs (one per year)
#   ./submit_catIII_max15.sh --single       # Submits all 600 jobs in 1 cluster
#   ./submit_catIII_max15.sh 2023           # Submits only 2023 (150 jobs)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

MODE="per-year"
if [ "$1" == "--single" ]; then
    MODE="single"
    shift
fi

YEAR_TARGET=""
if [[ "$1" =~ ^202[3-6]$ ]]; then
    YEAR_TARGET="$1"
    shift
fi

echo "======================================================================"
echo " Submitting Category III Top 10 Runs (15 Partitions/Run)"
echo " Total target jobs: 600 (150 jobs per year across 2023-2026)"
echo " Flavour:           longlunch"
echo "======================================================================"

if [ -n "${YEAR_TARGET}" ]; then
    echo "[INFO] Submitting Year ${YEAR_TARGET} (150 jobs)..."
    condor_submit "ref_times_${YEAR_TARGET}.sub" \
        args_file="${DIR}/args_partitions_catIII_${YEAR_TARGET}_max15.txt" \
        flavour="longlunch" \
        "$@"
elif [ "${MODE}" == "single" ]; then
    echo "[INFO] Submitting all 600 jobs under a single HTCondor cluster..."
    condor_submit ref_times.sub \
        args_file="${DIR}/args_partitions_catIII_max15.txt" \
        flavour="longlunch" \
        "$@"
else
    for Y in 2023 2024 2025 2026; do
        echo "[INFO] Submitting Year ${Y} (150 jobs)..."
        condor_submit "ref_times_${Y}.sub" \
            args_file="${DIR}/args_partitions_catIII_${Y}_max15.txt" \
            flavour="longlunch" \
            "$@"
    done
    echo "======================================================================"
    echo "[SUCCESS] Submitted all 4 years (600 jobs total) to HTCondor."
    echo "======================================================================"
fi
