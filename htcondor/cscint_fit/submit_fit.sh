#!/bin/bash
# ==============================================================================
# Submit Fit Jobs to HTCondor (Category II, Category III by year, or specific runs)
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="workday"
FORCE=0
DRY_RUN=0
SPECIFIC_RUNS=""
TARGET="catII"

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  catII                   Submit all 33 Cat II runs (default)
  2023 | catIII_2023      Submit 2023 Cat III runs (6079 - 6667)
  2024 | catIII_2024      Submit 2024 Cat III runs (8638 - 9880)
  2025 | catIII_2025      Submit 2025 Cat III runs (11124 - 12217)
  2026 | catIII_2026      Submit 2026 Cat III runs (13085 - 13520)
  catIII                  Submit all Cat III runs across 2023-2026 (40 runs)
  all                     Submit all Cat II and Cat III runs (73 runs)

Options:
  -y, --year YEAR         Select year: 2023, 2024, 2025, 2026
  -r, --run RUN(s)        Specific run number(s), comma-separated (e.g. 5119 or 5119,5120)
  -f, --force             Force re-fit even if output already exists on EOS
  --flavour FLAVOUR       HTCondor job flavour (default: workday)
  --dry-run               Display runs and settings without submitting
  -h, --help              Show this help message
EOF
    exit 0
}

# Parse positional target if given
if [[ $# -gt 0 ]] && [[ "$1" =~ ^(catII|catIII|2023|2024|2025|2026|catIII_2023|catIII_2024|catIII_2025|catIII_2026|all)$ ]]; then
    TARGET="$1"
    shift
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -y|--year) TARGET="$2"; shift 2 ;;
        -r|--run) SPECIFIC_RUNS="$2"; shift 2 ;;
        -f|--force) FORCE=1; shift ;;
        --flavour) FLAVOUR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p out err log

# Select args file based on target
case "${TARGET}" in
    catII)
        ARGS_FILE="${DIR}/args_catII.txt"
        ;;
    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_catIII_2023.txt"
        ;;
    2024|catIII_2024)
        ARGS_FILE="${DIR}/args_catIII_2024.txt"
        ;;
    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_catIII_2025.txt"
        ;;
    2026|catIII_2026)
        ARGS_FILE="${DIR}/args_catIII_2026.txt"
        ;;
    catIII)
        ARGS_FILE="${DIR}/args_catIII_all.txt"
        ;;
    all)
        ARGS_FILE="${DIR}/args_all.txt"
        cat "${DIR}/args_catII.txt" "${DIR}/args_catIII_all.txt" > "${ARGS_FILE}"
        ;;
    *)
        echo "[ERROR] Unknown target: ${TARGET}" >&2
        exit 1
        ;;
esac

SUBMIT_ARGS="${ARGS_FILE}"
if [ -n "${SPECIFIC_RUNS}" ]; then
    TMP_ARGS="${DIR}/args_custom_$$.txt"
    > "${TMP_ARGS}"
    IFS=',' read -ra RLIST <<< "${SPECIFIC_RUNS}"
    for r in "${RLIST[@]}"; do
        r_clean=$(echo "$r" | tr -dc '0-9')
        if [ -n "$r_clean" ]; then
            echo "$r_clean" >> "${TMP_ARGS}"
        fi
    done
    SUBMIT_ARGS="${TMP_ARGS}"
    trap 'rm -f "${TMP_ARGS}"' EXIT
fi

N_RUNS=$(wc -l < "${SUBMIT_ARGS}")
echo "======================================================================"
echo " Submitting cscint_fit Jobs to HTCondor"
echo " Target Group: ${TARGET}"
echo " Flavour:      ${FLAVOUR}"
echo " Force:        ${FORCE}"
echo " Total Runs:   ${N_RUNS}"
echo " Args File:    ${SUBMIT_ARGS}"
echo " Time:         $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run. Runs that would be queued:"
    cat "${SUBMIT_ARGS}"
    exit 0
fi

condor_submit cscint_fit.sub \
    args_file="${SUBMIT_ARGS}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_RUNS} jobs for ${TARGET}. Monitor with: condor_q"
echo "======================================================================"
