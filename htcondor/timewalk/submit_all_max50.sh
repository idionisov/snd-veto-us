#!/bin/bash
# ==============================================================================
# Submit Partition Jobs for Time-Walk Extraction (Max 50 Partitions/Run)
#
# Coverage:
#   - Category I  (2022) : 88 runs (2,841 jobs)
#   - Category II (2022) : 33 runs (1,478 jobs)
#   - Category III        : 40 runs (2,000 jobs, 10 runs/year x 2023-2026)
#   Total: 161 runs, 6,319 partition jobs
#
# Usage:
#   ./submit_all_max50.sh catII      # Submits Category II only (1,478 jobs) - RECOMMENDED FIRST
#   ./submit_all_max50.sh 2023       # Submits Category III 2023 only (500 jobs)
#   ./submit_all_max50.sh 2024       # Submits Category III 2024 only (500 jobs)
#   ./submit_all_max50.sh 2025       # Submits Category III 2025 only (500 jobs)
#   ./submit_all_max50.sh 2026       # Submits Category III 2026 only (500 jobs)
#   ./submit_all_max50.sh catIII     # Submits Category III only (2,000 jobs)
#   ./submit_all_max50.sh all        # Submits all categories (6,319 jobs)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="${1:-catII}"
shift || true

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"
OUT_BASE="${OUT_BASE:-/eos/user/i/idioniso/Timing/timewalk2/parts}"
CSCINT_FILE="${CSCINT_FILE:-/afs/cern.ch/work/i/idioniso/snd-veto-us/config/subsystem_cscint.json}"

echo "======================================================================"
echo " Submitting Time-Walk Partition Jobs (Max 50 Partitions/Run)"
echo " Target Category : ${TARGET}"
echo " Job Flavour     : ${FLAVOUR}"
echo " Force Reprocess : FORCE=${FORCE_FLAG}"
echo " c_scint File    : ${CSCINT_FILE}"
echo " Output Base     : ${OUT_BASE}"
echo " Time            : $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

case "${TARGET}" in
    catII|catii|CATII|II)
        ARGS_FILE="${DIR}/args_partitions_catII_max50.txt"
        echo "[INFO] Submitting Category II ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"
        ;;

    catI|cati|CATI|I)
        ARGS_FILE="${DIR}/args_partitions_catI_max50.txt"
        echo "[INFO] Submitting Category I ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"
        ;;

    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_partitions_catIII_2023_max50.txt"
        echo "[INFO] Submitting Category III 2023 ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"
        ;;

    2024|catIII_2024)
        ARGS_FILE="${DIR}/args_partitions_catIII_2024_max50.txt"
        echo "[INFO] Submitting Category III 2024 ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"
        ;;

    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_partitions_catIII_2025_max50.txt"
        echo "[INFO] Submitting Category III 2025 ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"
        ;;

    2026|catIII_2026)
        ARGS_FILE="${DIR}/args_partitions_catIII_2026_max50.txt"
        echo "[INFO] Submitting Category III 2026 ($(wc -l < "${ARGS_FILE}") jobs)..."
        condor_submit timewalk.sub \
            args_file="${ARGS_FILE}" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"
        ;;

    catIII|catiii|CATIII|III)
        for Y in 2023 2024 2025 2026; do
            ARGS_Y="${DIR}/args_partitions_catIII_${Y}_max50.txt"
            echo "[INFO] Submitting Category III Year ${Y} ($(wc -l < "${ARGS_Y}") jobs)..."
            condor_submit timewalk.sub \
                args_file="${ARGS_Y}" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                out_base="${OUT_BASE}" \
                cscint_file="${CSCINT_FILE}" \
                "$@"
        done
        ;;

    all|ALL)
        echo "[1/3] Submitting Category II ($(wc -l < args_partitions_catII_max50.txt) jobs)..."
        condor_submit timewalk.sub \
            args_file="${DIR}/args_partitions_catII_max50.txt" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"

        echo "[2/3] Submitting Category I ($(wc -l < args_partitions_catI_max50.txt) jobs)..."
        condor_submit timewalk.sub \
            args_file="${DIR}/args_partitions_catI_max50.txt" \
            flavour="${FLAVOUR}" \
            force="${FORCE_FLAG}" \
            out_base="${OUT_BASE}" \
            cscint_file="${CSCINT_FILE}" \
            "$@"

        echo "[3/3] Submitting Category III (40 runs, 2,000 jobs)..."
        for Y in 2023 2024 2025 2026; do
            ARGS_Y="${DIR}/args_partitions_catIII_${Y}_max50.txt"
            condor_submit timewalk.sub \
                args_file="${ARGS_Y}" \
                flavour="${FLAVOUR}" \
                force="${FORCE_FLAG}" \
                out_base="${OUT_BASE}" \
                cscint_file="${CSCINT_FILE}" \
                "$@"
        done
        ;;

    *)
        echo "[ERROR] Unknown target: '${TARGET}'. Valid options: catII, 2023, 2024, 2025, 2026, catIII, all" >&2
        exit 1
        ;;
esac

echo "======================================================================"
echo "[SUCCESS] HTCondor submission commands completed."
echo " Monitor with: condor_q   or   ./status_timewalk.sh"
echo "======================================================================"
