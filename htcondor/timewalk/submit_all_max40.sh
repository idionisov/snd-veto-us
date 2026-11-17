#!/bin/bash
# ==============================================================================
# Submit Partition Jobs for Time-Walk Extraction (Max 40 Partitions/Run)
#
# Coverage:
#   - Category I  (2022) : 88 runs (2,428 jobs)
#   - Category II (2022) : 33 runs (1,208 jobs)
#   - Category III        : 40 runs (1,600 jobs, 10 runs/year x 2023-2026)
#   Total: 161 runs, 5,236 partition jobs
#
# Usage:
#   ./submit_all_max40.sh            # Submits all categories
#   ./submit_all_max40.sh catII      # Submits Category II only (1,208 jobs)
#   ./submit_all_max40.sh catI       # Submits Category I only (2,428 jobs)
#   ./submit_all_max40.sh catIII     # Submits Category III only (1,600 jobs)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="${1:-catII}"
shift || true

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"

echo "======================================================================"
echo " Submitting Time-Walk Partition Jobs (Max 40 Partitions/Run)"
echo " Target Category : ${TARGET}"
echo " Job Flavour     : ${FLAVOUR}"
echo " Force Reprocess : FORCE=${FORCE_FLAG}"
echo "======================================================================"

case "${TARGET}" in
    catII|catii|CATII|II)
        ARGS_FILE="${DIR}/args_partitions_catII_max40.txt"
        echo "[INFO] Submitting Category II ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"
        ;;

    catI|cati|CATI|I)
        ARGS_FILE="${DIR}/args_partitions_catI_max40.txt"
        echo "[INFO] Submitting Category I ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"
        ;;

    catIII|catiii|CATIII|III)
        for Y in 2023 2024 2025 2026; do
            ARGS_Y="${DIR}/args_partitions_catIII_${Y}_max40.txt"
            echo "[INFO] Submitting Category III Year ${Y} ($(wc -l < "${ARGS_Y}") jobs)..."
            condor_submit timewalk.sub \
                args_file="${ARGS_Y}" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                "$@"
        done
        ;;

    all|ALL)
        echo "[1/3] Submitting Category II ($(wc -l < args_partitions_catII_max40.txt) jobs)..."
        condor_submit timewalk.sub \
            args_file="${DIR}/args_partitions_catII_max40.txt" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"

        echo "[2/3] Submitting Category I ($(wc -l < args_partitions_catI_max40.txt) jobs)..."
        condor_submit timewalk.sub \
            args_file="${DIR}/args_partitions_catI_max40.txt" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"

        echo "[3/3] Submitting Category III (40 runs, 1,600 jobs)..."
        for Y in 2023 2024 2025 2026; do
            ARGS_Y="${DIR}/args_partitions_catIII_${Y}_max40.txt"
            condor_submit timewalk.sub \
                args_file="${ARGS_Y}" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                "$@"
        done
        ;;

    *)
        echo "[ERROR] Unknown target: '${TARGET}'. Valid options: catII, catI, catIII, all" >&2
        exit 1
        ;;
esac

echo "======================================================================"
echo "[SUCCESS] HTCondor submission commands completed."
echo " Monitor with: condor_q   or   ./status_timewalk.sh"
echo "======================================================================"
