#!/bin/bash
# ==============================================================================
# Submit Category I Partition Jobs for Reference Time Extraction (Max 10/Run)
#
# Covers all 88 qualifying Category I runs (run <= 5116 and 5175 <= run <= 5192)
# Total jobs: 832
# Flavour: longlunch (default)
# Force: 1 (overwrites earlier extractions without veto/scifi1 cut)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

ARGS_FILE="${DIR}/args_partitions_catI_max10.txt"
if [ ! -f "${ARGS_FILE}" ]; then
    echo "[INFO] Generating ${ARGS_FILE}..."
    python3 "${DIR}/generate_args.py" -c catI -p 10 --from-existing
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")
FLAVOUR="${1:-longlunch}"
shift 1 2>/dev/null || shift $# 2>/dev/null || true

echo "======================================================================"
echo " Submitting Category I Partition Jobs (Max 10 Partitions/Run)"
echo " Total jobs: ${TOTAL_JOBS}"
echo " Arguments:  ${ARGS_FILE}"
echo " Flavour:    ${FLAVOUR}"
echo " Force:      1 (enforces veto / station 1 hit cut for Cat I)"
echo "======================================================================"

condor_submit ref_times.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="1" \
    "$@"
