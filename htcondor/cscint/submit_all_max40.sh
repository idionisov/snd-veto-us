#!/bin/bash
# ==============================================================================
# Submit Partition Jobs for cscint Extraction (Max 20 Partitions/Run)
#
# Coverage:
#   - Category I  (2022) : 88 runs (2,428 jobs)
#   - Category II (2022) : 33 runs (1,208 jobs)
#   - Category III        : 40 runs (1,600 jobs, 10 runs/year x 2023-2026)
#   Total: 161 runs, 5,236 partition jobs
#
# Usage:
#   ./submit_all_max40.sh            # Submits all categories (5,236 jobs in 3 clusters)
#   ./submit_all_max40.sh catI       # Submits Category I only (2,428 jobs)
#   ./submit_all_max40.sh catII      # Submits Category II only (1,208 jobs)
#   ./submit_all_max40.sh catIII     # Submits Category III only (1,600 jobs in 4 clusters)
#   ./submit_all_max40.sh 2026       # Submits Category III 2026 only (400 jobs)
#   ./submit_all_max40.sh --single   # Submits all 5,236 jobs in a single HTCondor cluster
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="${1:-all}"
shift || true

SINGLE_CLUSTER=0
if [ "${TARGET}" == "--single" ]; then
    SINGLE_CLUSTER=1
    TARGET="all"
fi

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-1}"

echo "======================================================================"
echo " Submitting cscint Partition Jobs (Max 20 Partitions/Run)"
echo " Reference Window: Adaptive / Dynamic (config/ref_time_windows.json)"
echo " Target Category : ${TARGET}"
echo " Job Flavour     : ${FLAVOUR}"
echo " Force Reprocess : FORCE=${FORCE_FLAG}"
echo "======================================================================"

case "${TARGET}" in
    all|ALL)
        if [ "${SINGLE_CLUSTER}" -eq 1 ]; then
            ARGS_FILE="${DIR}/args_partitions_all_max40.txt"
            TOTAL=$(wc -l < "${ARGS_FILE}")
            echo "[INFO] Submitting all ${TOTAL} jobs under 1 cluster..."
            condor_submit cscint.sub \
                args_file="${ARGS_FILE}" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                "$@"
        else
            echo "[1/3] Submitting Category I (88 runs, $(wc -l < args_partitions_catI_max40.txt) jobs)..."
            condor_submit cscint.sub \
                args_file="${DIR}/args_partitions_catI_max40.txt" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                "$@"

            echo "[2/3] Submitting Category II (33 runs, $(wc -l < args_partitions_catII_max40.txt) jobs)..."
            condor_submit cscint.sub \
                args_file="${DIR}/args_partitions_catII_max40.txt" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                "$@"

            echo "[3/3] Submitting Category III (40 runs, 1,600 jobs across 2023-2026)..."
            for Y in 2023 2024 2025 2026; do
                ARGS_Y="${DIR}/args_partitions_catIII_${Y}_max40.txt"
                echo "   -> Submitting Year ${Y} ($(wc -l < "${ARGS_Y}") jobs)..."
                condor_submit cscint.sub \
                    args_file="${ARGS_Y}" \
                    flavour="${FLAVOUR}" \
                    force="${FORCE_FLAG}" \
                    "$@"
            done
        fi
        ;;

    catI|cati|CATI|I)
        ARGS_FILE="${DIR}/args_partitions_catI_max40.txt"
        echo "[INFO] Submitting Category I ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit cscint.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"
        ;;

    catII|catii|CATII|II)
        ARGS_FILE="${DIR}/args_partitions_catII_max40.txt"
        echo "[INFO] Submitting Category II ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit cscint.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"
        ;;

    catIII|catiii|CATIII|III)
        for Y in 2023 2024 2025 2026; do
            ARGS_Y="${DIR}/args_partitions_catIII_${Y}_max40.txt"
            echo "[INFO] Submitting Category III Year ${Y} ($(wc -l < "${ARGS_Y}") jobs)..."
            condor_submit cscint.sub \
                args_file="${ARGS_Y}" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                "$@"
        done
        ;;

    2023|2024|2025|2026)
        ARGS_FILE="${DIR}/args_partitions_catIII_${TARGET}_max40.txt"
        echo "[INFO] Submitting Category III Year ${TARGET} ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit cscint.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            "$@"
        ;;

    *)
        echo "[ERROR] Unknown target: '${TARGET}'. Valid options: all, catI, catII, catIII, 2023, 2024, 2025, 2026" >&2
        exit 1
        ;;
esac

echo "======================================================================"
echo "[SUCCESS] HTCondor submission commands completed."
echo " Monitor with: condor_q   or   ./status_cscint.sh"
echo "======================================================================"
