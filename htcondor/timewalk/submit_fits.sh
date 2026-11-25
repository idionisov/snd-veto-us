#!/bin/bash
# ==============================================================================
# Submit Time-Walk Fitting HTCondor Jobs
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

IN_DIR="/eos/user/i/idioniso/Timing/timewalk2/runs"
OUT_DIR="/eos/user/i/idioniso/Timing/timewalk2/fits"
CSCINT_PATH="/afs/cern.ch/work/i/idioniso/snd-veto-us/config/subsystem_cscint.json"
OUT_ROOT_DIR="/eos/user/i/idioniso/Timing/timewalk2/fits_root"
FLAVOUR="workday"
FORCE=0
SAVE_CANVAS=1
DRY_RUN=0
CATEGORY="all"
SPECIFIC_RUNS=""
EXCLUDE_2024=0
YEAR=""
ONLY_MISSING=0

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  2024 | catIII_2024      Fit all 10 runs from 2024 (8638 - 9880)
  missing                 Fit only runs whose merged ROOT exists but fit JSON is missing
  catII                   Fit Cat II (2022) runs
  catIII                  Fit Cat III runs across all years
  all                     Fit all candidate runs (default)

Options:
  -c, --category CAT      Filter runs by category: catI, catII, catIII, or all
  -y, --year YEAR         Filter runs by year (e.g. 2022, 2023, 2024, 2025, 2026)
  -r, --run RUN(s)        Specific run number, or comma-separated list (e.g. 8638 or 8638,8724)
  -m, --missing           Submit only missing fits
  --exclude-2024          Exclude 2024 runs (runs 8000-9999)
  -f, --force             Force re-fitting even if output JSON already exists
  --flavour FLAVOUR       HTCondor JobFlavour (default: workday)
  --no-canvas             Do not store fit canvases in ROOT file (faster execution)
  --dry-run               Create args file and display candidate jobs without submitting
  --in-dir DIR            Input directory with run ROOT files (default: ${IN_DIR})
  --out-dir DIR           Output directory for fit JSONs (default: ${OUT_DIR})
  --out-root-dir DIR      Output directory for updated ROOT files (default: ${OUT_ROOT_DIR})
  --cscint-file FILE      Path or directory for c_scint constants (default: ${CSCINT_PATH})
  --cscint-dir DIR        Alias for --cscint-file
  -h, --help              Show this help message
EOF
    exit 0
}

# Parse positional argument if given
if [[ $# -gt 0 ]] && [[ "$1" =~ ^(missing|2022|2023|2024|2025|2026|catI|catII|catIII|catIII_2023|catIII_2024|catIII_2025|catIII_2026|all)$ ]]; then
    case "$1" in
        missing) ONLY_MISSING=1 ;;
        2022) YEAR="2022" ;;
        2023|catIII_2023) YEAR="2023" ;;
        2024|catIII_2024) YEAR="2024" ;;
        2025|catIII_2025) YEAR="2025" ;;
        2026|catIII_2026) YEAR="2026" ;;
        catI) CATEGORY="catI" ;;
        catII) CATEGORY="catII" ;;
        catIII) CATEGORY="catIII" ;;
        all) CATEGORY="all" ;;
    esac
    shift
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--category) CATEGORY="$2"; shift 2 ;;
        -y|--year) YEAR="$2"; shift 2 ;;
        -m|--missing) ONLY_MISSING=1; shift ;;
        -r|--run) SPECIFIC_RUNS="$2"; shift 2 ;;
        --exclude-2024|--no-2024) EXCLUDE_2024=1; shift ;;
        -f|--force) FORCE=1; shift ;;
        --flavour) FLAVOUR="$2"; shift 2 ;;
        --no-canvas) SAVE_CANVAS=0; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        --in-dir) IN_DIR="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        --out-root-dir) OUT_ROOT_DIR="$2"; shift 2 ;;
        --cscint-file|--cscint-dir) CSCINT_PATH="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p out err log "${OUT_DIR}" "${OUT_ROOT_DIR}"

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

get_year() {
    local r="$1"
    if [ "$r" -ge 5000 ] && [ "$r" -lt 6000 ]; then
        echo "2022"
    elif [ "$r" -ge 6000 ] && [ "$r" -lt 7000 ]; then
        echo "2023"
    elif [ "$r" -ge 8000 ] && [ "$r" -lt 10000 ]; then
        echo "2024"
    elif [ "$r" -ge 10000 ] && [ "$r" -lt 13000 ]; then
        echo "2025"
    elif [ "$r" -ge 13000 ] && [ "$r" -lt 14000 ]; then
        echo "2026"
    else
        echo "other"
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
        
        if [ "${EXCLUDE_2024}" -eq 1 ] && [ "$r" -ge 8000 ] && [ "$r" -lt 10000 ]; then
            continue
        fi

        if [ -n "${YEAR}" ]; then
            ryear=$(get_year "$r")
            if [ "${ryear}" != "${YEAR}" ]; then
                continue
            fi
        fi

        rcat=$(get_cat "$r")
        if [ "${CATEGORY}" != "all" ] && [ "${CATEGORY,,}" != "${rcat,,}" ]; then
            continue
        fi

        if [ "${ONLY_MISSING}" -eq 1 ]; then
            jf="${OUT_DIR}/run${r}_timing_calibration.json"
            rf="${OUT_ROOT_DIR}/run${r}.root"
            if [ -f "$jf" ] && [ -f "$rf" ] && [ $(stat -c%s "$jf" 2>/dev/null || echo 0) -gt 1000 ]; then
                continue
            fi
        fi

        echo "$r" >> "${ARGS_FILE}"
    done
fi

TOTAL_CANDIDATES=$(wc -l < "${ARGS_FILE}" 2>/dev/null || echo 0)

if [ "${TOTAL_CANDIDATES}" -eq 0 ]; then
    echo "[INFO] No runs to submit with current filters. Everything up to date!"
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
echo " Input Directory:      ${IN_DIR}"
echo " Output Directory:     ${OUT_DIR}"
echo " Destination ROOT:     ${OUT_ROOT_DIR}"
echo " c_scint Constants:    ${CSCINT_PATH}"
echo " Category Filter:      ${CATEGORY}"
echo " Year Filter:          ${YEAR:-all}"
echo " Only Missing:         ${ONLY_MISSING}"
echo " Total Runs to Queue:  ${TOTAL_CANDIDATES}"
echo " Already Fitted (EOS): ${ALREADY_FITTED}"
echo " Force Re-fit:         ${FORCE}"
echo " Flavour:              ${FLAVOUR}"
echo " Args File:            ${ARGS_FILE}"
echo " Time:                 $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. Runs queued in ${ARGS_FILE}:"
    cat "${ARGS_FILE}"
    echo "[INFO] Submit skipped."
    exit 0
fi

condor_submit fit_timewalk.sub \
    args_file="${ARGS_FILE}" \
    in_dir="${IN_DIR}" \
    out_dir="${OUT_DIR}" \
    out_root_dir="${OUT_ROOT_DIR}" \
    cscint_dir="${CSCINT_PATH}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}" \
    save_canvas="${SAVE_CANVAS}"

echo "======================================================================"
echo "[SUCCESS] Submitted ${TOTAL_CANDIDATES} fit jobs to HTCondor."
echo " Monitor with: condor_q or ./status_fits.sh"
echo "======================================================================"
