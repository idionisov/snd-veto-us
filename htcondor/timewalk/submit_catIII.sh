#!/bin/bash
# ==============================================================================
# Submit Category III Partition Jobs for Time-Walk Extraction (2023-2026)
#
# Usage:
#   ./submit_catIII.sh              # Submits all 40 runs (800 jobs, 2023-2026)
#   ./submit_catIII.sh 2023         # Submits 2023 runs only (200 jobs)
#   ./submit_catIII.sh 2024         # Submits 2024 runs only (200 jobs)
#   ./submit_catIII.sh 2025         # Submits 2025 runs only (200 jobs)
#   ./submit_catIII.sh 2026         # Submits 2026 runs only (200 jobs)
#
# Options:
#   FORCE=1 ./submit_catIII.sh      # Force reprocessing of already existing parts
#   FLAVOUR=longlunch ./submit_catIII.sh
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

YEAR="${1:-all}"
if [[ "${YEAR}" =~ ^(2023|2024|2025|2026)$ ]]; then
    shift || true
    ARGS_FILE="${DIR}/args_partitions_catIII_${YEAR}_max20.txt"
    DESC="Year ${YEAR}"
else
    ARGS_FILE="${DIR}/args_partitions_catIII_max20.txt"
    DESC="All Years (2023-2026, 40 runs)"
fi

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"

echo "======================================================================"
echo " Submitting Category III Partition Jobs for Time-Walk (${DESC})"
echo " Total jobs: $(wc -l < "${ARGS_FILE}")"
echo " Args File:  ${ARGS_FILE}"
echo " Flavour:    ${FLAVOUR}"
echo " Force:      ${FORCE_FLAG}"
echo "======================================================================"

condor_submit timewalk.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE_FLAG}" \
    "$@"

echo "======================================================================"
echo "[SUCCESS] Category III submission complete."
echo " Monitor with: condor_q   or   ./status_timewalk.sh"
echo "======================================================================"
