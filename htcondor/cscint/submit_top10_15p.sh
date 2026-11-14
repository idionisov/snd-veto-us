#!/bin/bash
# ==============================================================================
# Submit Category III Top 10 Runs for cscint (Max 15 Partitions/Run, 600 jobs)
#
# Usage:
#   ./submit_top10_15p.sh                # Submits all 4 years (600 jobs in 4 clusters)
#   ./submit_top10_15p.sh --single       # Submits all 600 jobs in 1 cluster
#   ./submit_top10_15p.sh 2026           # Submits only 2026 (150 jobs)
#   ./submit_top10_15p.sh 2023           # Submits only 2023 (150 jobs)
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
echo " Submitting Category III Top 10 Runs for cscint (15 Partitions/Run)"
echo " Total target jobs: 600 (150 jobs per year across 2023-2026)"
echo " Flavour:           workday"
echo "======================================================================"

if [ -n "${YEAR_TARGET}" ]; then
    ARGS_FILE="${DIR}/args_partitions_catIII_${YEAR_TARGET}_max15.txt"
    if [ ! -f "${ARGS_FILE}" ]; then
        echo "[INFO] ${ARGS_FILE} not found. Generating argument lists..."
        python3 "${DIR}/generate_args.py" -c catIII -p 15
    fi
    TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")
    echo "[INFO] Submitting Year ${YEAR_TARGET} (${TOTAL_JOBS} jobs)..."
    condor_submit cscint.sub \
        args_file="${ARGS_FILE}" \
        flavour="workday" \
        "$@"
elif [ "${MODE}" == "single" ]; then
    ARGS_FILE="${DIR}/args_partitions_catIII_max15.txt"
    if [ ! -f "${ARGS_FILE}" ]; then
        echo "[INFO] ${ARGS_FILE} not found. Generating argument lists..."
        python3 "${DIR}/generate_args.py" -c catIII -p 15
    fi
    TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")
    echo "[INFO] Submitting all ${TOTAL_JOBS} jobs under a single HTCondor cluster..."
    condor_submit cscint.sub \
        args_file="${ARGS_FILE}" \
        flavour="workday" \
        "$@"
else
    for Y in 2023 2024 2025 2026; do
        ARGS_FILE="${DIR}/args_partitions_catIII_${Y}_max15.txt"
        if [ ! -f "${ARGS_FILE}" ]; then
            python3 "${DIR}/generate_args.py" -c catIII -p 15
        fi
        TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")
        echo "[INFO] Submitting Year ${Y} (${TOTAL_JOBS} jobs)..."
        condor_submit cscint.sub \
            args_file="${ARGS_FILE}" \
            flavour="workday" \
            "$@"
    done
    echo "======================================================================"
    echo "[SUCCESS] Submitted all 4 years (600 jobs total) to HTCondor."
    echo "======================================================================"
fi
