#!/bin/bash
# ==============================================================================
# Submit Category III Partition Jobs for Time-Walk Extraction (2023-2026)
#
# Usage:
#   # By default (max40 partitions/run, 400 jobs per year):
#   ./submit_catIII.sh 2023         # Submits 2023 runs (400 jobs)
#   ./submit_catIII.sh 2024         # Submits 2024 runs (400 jobs)
#   ./submit_catIII.sh 2025         # Submits 2025 runs (400 jobs)
#   ./submit_catIII.sh 2026         # Submits 2026 runs (400 jobs)
#   ./submit_catIII.sh all          # Submits all 2023-2026 runs (1,600 jobs)
#
#   # Full partitions mode (--all):
#   ./submit_catIII.sh 2023 --all   # Submits ALL partitions for 2023 (2,914 jobs)
#   ./submit_catIII.sh 2024 --all   # Submits ALL partitions for 2024 (5,722 jobs)
#   ./submit_catIII.sh 2025 --all   # Submits ALL partitions for 2025 (3,987 jobs)
#   ./submit_catIII.sh 2026 --all   # Submits ALL partitions for 2026 (3,931 jobs)
#
# Options:
#   FORCE=1 ./submit_catIII.sh 2023      # Force reprocessing of already existing parts
#   FLAVOUR=longlunch ./submit_catIII.sh 2023
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

YEAR="all"
USE_ALL=0

for arg in "$@"; do
    if [[ "${arg}" =~ ^(2023|2024|2025|2026|all)$ ]]; then
        YEAR="${arg}"
    elif [ "${arg}" = "--all" ] || [ "${arg}" = "all_parts" ]; then
        USE_ALL=1
    fi
done

if [ "${USE_ALL}" = "1" ] || [ "${ALL:-0}" = "1" ]; then
    P_SUFFIX="all"
elif [ -f "${DIR}/args_partitions_catIII_max40.txt" ]; then
    P_SUFFIX="max40"
else
    P_SUFFIX="max20"
fi

if [[ "${YEAR}" =~ ^(2023|2024|2025|2026)$ ]]; then
    ARGS_FILE="${DIR}/args_partitions_catIII_${YEAR}_${P_SUFFIX}.txt"
    DESC="Year ${YEAR} (${P_SUFFIX})"
else
    ARGS_FILE="${DIR}/args_partitions_catIII_${P_SUFFIX}.txt"
    DESC="All Years (2023-2026, 40 runs, ${P_SUFFIX})"
fi

if [ ! -f "${ARGS_FILE}" ]; then
    echo "[ERROR] Args file not found: ${ARGS_FILE}" >&2
    exit 1
fi

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"

# Filter out YEAR and --all flags from extra args passed to condor_submit
PASSTHROUGH_ARGS=()
for a in "$@"; do
    if [[ ! "${a}" =~ ^(2023|2024|2025|2026|all|--all|all_parts)$ ]]; then
        PASSTHROUGH_ARGS+=("${a}")
    fi
done

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
    "${PASSTHROUGH_ARGS[@]}"

echo "======================================================================"
echo "[SUCCESS] Category III (${YEAR}, ${P_SUFFIX}) submission complete."
echo " Monitor with: condor_q   or   ./status_timewalk.sh"
echo "======================================================================"
