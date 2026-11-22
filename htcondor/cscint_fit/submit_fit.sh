#!/bin/bash
# ==============================================================================
# Submit Time-Walk / cscint Fit Jobs to HTCondor
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="workday"
FORCE=0
DRY_RUN=0
SPECIFIC_RUNS=""
ARGS_FILE="${DIR}/args_catII.txt"

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  -r, --run RUN(s)        Specific run number(s), comma-separated (e.g. 5119 or 5119,5120)
  -f, --force             Force re-fit even if output already exists on EOS
  --flavour FLAVOUR       HTCondor job flavour (default: workday)
  --dry-run               Display runs and settings without submitting
  -h, --help              Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--run) SPECIFIC_RUNS="$2"; shift 2 ;;
        -f|--force) FORCE=1; shift ;;
        --flavour) FLAVOUR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p out err log

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
echo " Flavour:     ${FLAVOUR}"
echo " Force:       ${FORCE}"
echo " Total Runs:  ${N_RUNS}"
echo " Args File:   ${SUBMIT_ARGS}"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
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
echo "[SUCCESS] Submitted ${N_RUNS} jobs. Monitor with: condor_q"
echo "======================================================================"
