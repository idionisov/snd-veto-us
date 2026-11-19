#!/bin/bash
# ==============================================================================
# Submit Category III Top 10 Runs (Max 5 Partitions/Run, 200 jobs total)
#
# Usage:
#   ./submit_catIII_max5.sh                # Submits 4 clusters of 50 jobs (one per year)
#   ./submit_catIII_max5.sh --single       # Submits all 200 jobs in 1 cluster
#   ./submit_catIII_max5.sh 2023           # Submits only 2023 (50 jobs)
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
echo " Submitting Category III Top 10 Runs (5 Partitions/Run)"
echo " Total target jobs: 200 (50 jobs per year across 2023-2026)"
echo " Flavour:           longlunch"
echo "======================================================================"

if [ -n "${YEAR_TARGET}" ]; then
    ARGS_FILE="${DIR}/args_partitions_catIII_${YEAR_TARGET}_max5.txt"
    echo "[INFO] Submitting Year ${YEAR_TARGET} (50 jobs from ${ARGS_FILE})..."
    condor_submit ref_times.sub \
        args_file="${ARGS_FILE}" \
        flavour="longlunch" \
        "$@"
elif [ "${MODE}" == "single" ]; then
    ARGS_FILE="${DIR}/args_partitions_catIII_max5.txt"
    echo "[INFO] Submitting all 200 jobs under a single HTCondor cluster..."
    condor_submit ref_times.sub \
        args_file="${ARGS_FILE}" \
        flavour="longlunch" \
        "$@"
else
    for Y in 2023 2024 2025 2026; do
        ARGS_FILE="${DIR}/args_partitions_catIII_${Y}_max5.txt"
        echo "[INFO] Submitting Year ${Y} (50 jobs from ${ARGS_FILE})..."
        condor_submit ref_times.sub \
        args_file="${ARGS_FILE}" \
            flavour="longlunch" \
            "$@"
    done
    echo "======================================================================"
    echo "[SUCCESS] Submitted all 4 years (200 jobs total) to HTCondor."
    echo "======================================================================"
fi
