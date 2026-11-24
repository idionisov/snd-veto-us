#!/bin/bash
# ==============================================================================
# Submit Partition Jobs for Time-Walk Extraction (Iteration 2 with cscint_tw)
#
# Available Coverage (66 runs with cscint_tw fits):
#   - Category II (2022) : 33 runs (1,478 jobs)
#   - Category III (2023): 10 runs (500 jobs)
#   - Category III (2024): 10 runs (500 jobs)
#   - Category III (2025): 10 runs (500 jobs)
#   - Category III (2026): 3 runs (137 jobs)
#
# Usage:
#   ./submit_partitions.sh catII      # Category II (1,478 jobs)
#   ./submit_partitions.sh 2023       # Category III 2023 (500 jobs)
#   ./submit_partitions.sh 2024       # Category III 2024 (500 jobs)
#   ./submit_partitions.sh 2025       # Category III 2025 (500 jobs)
#   ./submit_partitions.sh 2026       # Category III 2026 (137 jobs)
#   ./submit_partitions.sh all        # All runs
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  catII | 2022            Category II (2022)
  2023 | catIII_2023      Category III (2023)
  2024 | catIII_2024      Category III (2024)
  2025 | catIII_2025      Category III (2025)
  2026 | catIII_2026      Category III (2026)
  all                     All available runs

Options:
  --flavour FLAVOUR       HTCondor job flavour (default: workday)
  --dry-run               Display jobs without submitting
  -h, --help              Show this help
EOF
    exit 0
}

TARGET="all"
FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"
DRY_RUN=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage ;;
        --dry-run)
            DRY_RUN=1; shift ;;
        --flavour)
            FLAVOUR="$2"; shift 2 ;;
        catII|catii|CATII|2022|2023|catIII_2023|2024|catIII_2024|2025|catIII_2025|2026|catIII_2026|all|ALL)
            TARGET="$1"; shift ;;
        *)
            echo "[ERROR] Unknown target or option: $1" >&2
            echo "Valid targets: catII, 2023, 2024, 2025, 2026, all" >&2
            exit 1 ;;
    esac
done

CSCINT_DIR="${CSCINT_DIR:-/eos/user/i/idioniso/Timing/cscint_tw/fits}"
OUT_BASE="${OUT_BASE:-/eos/user/i/idioniso/Timing/timewalk_tw_parts}"

case "${TARGET}" in
    catII|catii|CATII|2022)
        ARGS_FILE="${DIR}/args_partitions_catII_max50.txt"
        ;;
    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_partitions_catIII_2023_max50.txt"
        ;;
    2024|catIII_2024)
        ARGS_FILE="${DIR}/args_partitions_catIII_2024_max50.txt"
        ;;
    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_partitions_catIII_2025_max50.txt"
        ;;
    2026|catIII_2026)
        ARGS_FILE="${DIR}/args_partitions_catIII_2026_max50.txt"
        ;;
    all|ALL)
        ARGS_FILE="${DIR}/args_partitions_all_max50.txt"
        ;;
    *)
        echo "[ERROR] Unknown target: ${TARGET}" >&2
        echo "Valid targets: catII, 2023, 2024, 2025, 2026, all" >&2
        exit 1
        ;;
esac

N_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Time-Walk Partition Jobs (Iteration 2: cscint_tw)"
echo " Target Category : ${TARGET}"
echo " Total Jobs      : ${N_JOBS}"
echo " Job Flavour     : ${FLAVOUR}"
echo " Force Reprocess : FORCE=${FORCE_FLAG}"
echo " c_scint Fits    : ${CSCINT_DIR}"
echo " Destination     : ${OUT_BASE}"
echo " Args File       : ${ARGS_FILE}"
echo " Time            : $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. Exiting without submitting."
    exit 0
fi

condor_submit timewalk.sub     args_file="${ARGS_FILE}"     flavour="${FLAVOUR}"     force="${FORCE_FLAG}"     cscint_dir="${CSCINT_DIR}"     out_base="${OUT_BASE}"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_JOBS} partition jobs for target '${TARGET}'."
echo " Monitor with: condor_q or ./status_partitions.sh"
echo "======================================================================"
