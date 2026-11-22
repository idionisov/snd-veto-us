#!/bin/bash
# ==============================================================================
# Submit Category II Partition Jobs for Time-Walk Extraction
# Usage:
#   ./submit_catII.sh          # Defaults to max40 (or max20)
#   ./submit_catII.sh --all    # Submits all 3,389 partitions across all Cat II runs
#   ./submit_catII.sh <args_file>
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"

if [ "${1:-}" = "--all" ] || [ "${ALL:-0}" = "1" ]; then
    ARGS_FILE="${DIR}/args_partitions_catII_all.txt"
    shift || true
elif [ -n "${1:-}" ] && [ -f "${1}" ]; then
    ARGS_FILE="${1}"
    shift
elif [ -n "${ARGS_FILE:-}" ] && [ -f "${ARGS_FILE}" ]; then
    :
else
    # Prefer max40, fallback to max20
    ARGS_FILE="${DIR}/args_partitions_catII_max40.txt"
    if [ ! -f "${ARGS_FILE}" ]; then
        ARGS_FILE="${DIR}/args_partitions_catII_max20.txt"
    fi
fi

if [ ! -f "${ARGS_FILE}" ]; then
    echo "[ERROR] Args file not found: ${ARGS_FILE}" >&2
    exit 1
fi

echo "======================================================================"
echo " Submitting Category II Partition Jobs for Time-Walk"
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
