#!/bin/bash
# ==============================================================================
# Submit Time-Walk Corrected c_scint Fit Jobs to HTCondor
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="workday"
FORCE=0
DRY_RUN=0
SPECIFIC_RUNS=""
TARGET="all"

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  all                     Submit all available merged runs in cscint_tw/runs (default: 53 runs)
  missing                 Submit only missing/incomplete runs
  catII                   Submit Cat II (2022) runs (33 runs)
  2023 | catIII_2023      Submit Cat III 2023 runs (10 runs)
  2025 | catIII_2025      Submit Cat III 2025 runs (10 runs)

Options:
  -r, --run RUN(s)        Specific run number(s), comma-separated (e.g. 5119 or 5119,5120)
  -f, --force             Force re-fit even if output already exists on EOS
  --flavour FLAVOUR       HTCondor job flavour (default: workday)
  --dry-run               Display runs and settings without submitting
  -h, --help              Show this help message
EOF
    exit 0
}

# Parse positional target if given
if [[ $# -gt 0 ]] && [[ "$1" =~ ^(all|missing|catII|catIII_2023|catIII_2025|2023|2025)$ ]]; then
    TARGET="$1"
    shift
fi

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

# Refresh missing args file
generate_missing() {
    local missing_file="${DIR}/args_fit_missing.txt"
    > "${missing_file}"
    while read -r r; do
        [ -z "$r" ] && continue
        local jf="/eos/user/i/idioniso/Timing/cscint_tw/fits/run${r}_cscint.json"
        local rf="/eos/user/i/idioniso/Timing/cscint_tw/fits_root/run${r}.root"
        if [ ! -f "$jf" ] || [ ! -f "$rf" ]; then
            echo "$r" >> "${missing_file}"
        fi
    done < "${DIR}/args_fit_all.txt"
}

case "${TARGET}" in
    all)
        ARGS_FILE="${DIR}/args_fit_all.txt"
        ;;
    missing)
        generate_missing
        ARGS_FILE="${DIR}/args_fit_missing.txt"
        ;;
    catII)
        ARGS_FILE="${DIR}/args_fit_catII.txt"
        ;;
    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_fit_catIII_2023.txt"
        ;;
    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_fit_catIII_2025.txt"
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

N_RUNS=$(wc -l < "${SUBMIT_ARGS}" 2>/dev/null || echo 0)

if [ "${N_RUNS}" -eq 0 ]; then
    echo "[INFO] No runs to submit for target '${TARGET}'. Everything up to date!"
    exit 0
fi

echo "======================================================================"
echo " Submitting cscint_tw Fit Jobs to HTCondor"
echo " Target Group: ${TARGET}"
echo " Flavour:      ${FLAVOUR}"
echo " Force:        ${FORCE}"
echo " Total Runs:   ${N_RUNS}"
echo " Args File:    ${SUBMIT_ARGS}"
echo " Destination:  JSON -> /eos/user/i/idioniso/Timing/cscint_tw/fits"
echo "               ROOT -> /eos/user/i/idioniso/Timing/cscint_tw/fits_root"
echo " Time:         $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run. Runs that would be queued:"
    cat "${SUBMIT_ARGS}"
    exit 0
fi

condor_submit fit.sub \
    args_file="${SUBMIT_ARGS}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_RUNS} jobs for ${TARGET}. Monitor with: condor_q or ./status_fit.sh"
echo "======================================================================"
