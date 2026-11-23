#!/bin/bash
# ==============================================================================
# Submit Time-Walk Fitting HTCondor Jobs
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

IN_DIR="/eos/user/i/idioniso/Timing/timewalk/runs"
OUT_DIR="/eos/user/i/idioniso/Timing/timewalk/fits"
CSCINT_DIR="/eos/user/i/idioniso/Timing/cscint/fits"
OUT_ROOT_DIR="/eos/user/i/idioniso/Timing/timewalk/fits_root"
FLAVOUR="workday"
FORCE=0
SAVE_CANVAS=1
DRY_RUN=0
CATEGORY="all"
SPECIFIC_RUNS=""

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  -c, --category CAT      Filter runs by category: catI, catII, catIII, or all (default: all)
  -r, --run RUN(s)        Specific run number, or comma-separated list (e.g. 5119 or 5119,5120)
  -f, --force             Force re-fitting even if output JSON already exists
  --flavour FLAVOUR       HTCondor JobFlavour (default: workday)
  --no-canvas             Do not store fit canvases in ROOT file (faster execution)
  --dry-run               Create args file and display candidate jobs without submitting
  --in-dir DIR            Input directory with run ROOT files (default: ${IN_DIR})
  --out-dir DIR           Output directory for fit JSONs (default: ${OUT_DIR})
  --out-root-dir DIR      Output directory for updated ROOT files (default: ${OUT_ROOT_DIR})
  --cscint-dir DIR        Directory for c_scint constants (default: ${CSCINT_DIR})
  -h, --help              Show this help message
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--category) CATEGORY="$2"; shift 2 ;;
        -r|--run) SPECIFIC_RUNS="$2"; shift 2 ;;
        -f|--force) FORCE=1; shift ;;
        --flavour) FLAVOUR="$2"; shift 2 ;;
        --no-canvas) SAVE_CANVAS=0; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --in-dir) IN_DIR="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --out-root-dir) OUT_ROOT_DIR="$2"; shift 2 ;;
        --cscint-dir) CSCINT_DIR="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p out err log "${OUT_DIR}"

# Helper function to categorize run number
get_cat() {
    local r="$1"
    if [ "$r" -le 5116 ] || { [ "$r" -ge 5175 ] && [ "$r" -le 5192 ]; }; then
        echo "catI"
    elif { [ "$r" -ge 5117 ] && [ "$r" -le 5174 ]; } || { [ "$r" -ge 5193 ] && [ "$r" -le 5412 ]; }; then
        echo "catII"
    else
        echo "catIII"
    fi
}

# Collect candidate runs
ARGS_FILE="${DIR}/args_fits.txt"
> "${ARGS_FILE}"

if [ -n "${SPECIFIC_RUNS}" ]; then
    IFS=',' read -ra RLIST <<< "${SPECIFIC_RUNS}"
    for r in "${RLIST[@]}"; do
        r_clean=$(echo "$r" | tr -dc '0-9')
        if [ -n "$r_clean" ]; then
            echo "$r_clean" >> "${ARGS_FILE}"
        fi
    done
else
    # Scan input directory for run files
    for f in $(ls -1 "${IN_DIR}"/run*.root 2>/dev/null | sort -V); do
        r=$(basename "$f" | sed -E 's/run([0-9]+)\.root/\1/')
        if [[ ! "$r" =~ ^[0-9]+$ ]]; then continue; fi
        
        rcat=$(get_cat "$r")
        if [ "${CATEGORY}" == "all" ] || [ "${CATEGORY,,}" == "${rcat,,}" ]; then
            echo "$r" >> "${ARGS_FILE}"
        fi
    done
fi

TOTAL_CANDIDATES=$(wc -l < "${ARGS_FILE}")

if [ "${TOTAL_CANDIDATES}" -eq 0 ]; then
    echo "[WARNING] No matching runs found in ${IN_DIR} for category '${CATEGORY}'."
    exit 0
fi

# Count existing fits
ALREADY_FITTED=0
while read -r r; do
    if [ -f "${OUT_DIR}/run${r}_timing_calibration.json" ]; then
        ALREADY_FITTED=$((ALREADY_FITTED + 1))
    fi
done < "${ARGS_FILE}"

echo "======================================================================"
echo " SND@LHC Time-Walk Fitting HTCondor Submission"
echo " Input Directory:  ${IN_DIR}"
echo " Output Directory: ${OUT_DIR}"
echo " Category Filter:  ${CATEGORY}"
echo " Total Candidate Runs: ${TOTAL_CANDIDATES}"
echo " Already Fitted:       ${ALREADY_FITTED}"
echo " Force Re-fit:         ${FORCE}"
echo " Flavour:              ${FLAVOUR}"
echo " Args File:            ${ARGS_FILE}"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. Runs queued in ${ARGS_FILE}:"
    head -n 15 "${ARGS_FILE}"
    if [ "${TOTAL_CANDIDATES}" -gt 15 ]; then
        echo " ... ($((TOTAL_CANDIDATES - 15)) more runs)"
    fi
    echo "[INFO] Submit skipped."
    exit 0
fi

condor_submit fit_timewalk.sub \
    args_file="${ARGS_FILE}" \
    in_dir="${IN_DIR}" \
    out_dir="${OUT_DIR}" \
    out_root_dir="${OUT_ROOT_DIR}" \
    cscint_dir="${CSCINT_DIR}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}" \
    save_canvas="${SAVE_CANVAS}"
