#!/bin/bash
set -eo pipefail

# ==============================================================================
# merge_and_fit.sh: Merge 250 parallel raw histogram files & perform final fits
#
# Usage:
#   ./merge_and_fit.sh             # Merge all parts & fit final parameters
#   ./merge_and_fit.sh --merge     # Only merge raw histograms with hadd
#   ./merge_and_fit.sh --fit       # Only fit already-merged histograms
# ==============================================================================

# Default run is 5999, but accept -r/--run or positional run number
RUN="5999"
DO_MERGE=1
DO_FIT=1
DO_FIT_SPEED=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -r|--run)
            RUN="$2"
            shift 2
            ;;
        --merge)
            DO_FIT=0
            shift
            ;;
        --fit)
            DO_MERGE=0
            shift
            ;;
        --fit-speed)
            DO_FIT_SPEED=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-r|--run <run_number>] [--merge] [--fit] [--fit-speed]"
            exit 0
            ;;
        *)
            if [[ "$1" =~ ^[0-9]+$ ]]; then
                RUN="$1"
                shift
            else
                shift
            fi
            ;;
    esac
done

RUN_STR=$(printf "%06d" "${RUN}")
OUT_DIR="${OUT_DIR:-/eos/user/i/idioniso/Timing/run${RUN_STR}}"
PARALLEL_DIR="${PARALLEL_DIR:-${OUT_DIR}/parallel_parts}"
MERGED_ROOT="${MERGED_ROOT:-${OUT_DIR}/merged_raw_histograms.root}"
CSCINT_FILE="${CSCINT_FILE:-${OUT_DIR}/run${RUN_STR}_cscintvalues.json}"
CSCINT_RAW="${CSCINT_RAW:-${OUT_DIR}/raw_cscint_histograms.root}"
N_EXPECTED="${N_EXPECTED:-250}"
REFERENCESYSTEM="${REFERENCESYSTEM:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
    source "${SCRIPT_DIR}/sndswEnv.sh"
fi

PY_RUN="/afs/cern.ch/user/i/idioniso/snd_master/sndsw/shipLHC/scripts/run_TimeWalk.py"

echo "======================================================================"
echo " TimeWalk Merger & Final Fitting Pipeline"
echo " Run:                 ${RUN}"
echo " Expected Partitions: ${N_EXPECTED}"
echo " Parallel Directory:  ${PARALLEL_DIR}"
echo " Merged ROOT File:    ${MERGED_ROOT}"
echo " Output Directory:    ${OUT_DIR}"
echo "======================================================================"

# ------------------------------------------------------------------------------
# STEP 3: Merge raw histograms across all jobs with hadd
# ------------------------------------------------------------------------------
if [ "${DO_MERGE}" -eq 1 ]; then
    echo ""
    echo "[STEP 3/4] Collecting raw histograms across all ${N_EXPECTED} jobs..."
    RAW_FILES=()

    if [ -f "${CSCINT_RAW}" ]; then
        echo "  + Including Step 1 raw histograms: ${CSCINT_RAW}"
        RAW_FILES+=("${CSCINT_RAW}")
    fi

    for i in $(seq 0 $((N_EXPECTED - 1))); do
        RAW_FILE=$(find "${PARALLEL_DIR}/part_${i}" -name "raw_histograms_*.root" 2>/dev/null | head -n 1)
        if [ -z "${RAW_FILE}" ] || [ ! -f "${RAW_FILE}" ]; then
            RAW_FILE=$(find "${PARALLEL_DIR}/speed_part_${i}" -name "raw_cscint_*.root" 2>/dev/null | head -n 1)
        fi
        if [ -f "${RAW_FILE}" ] && [ $(stat -c%s "${RAW_FILE}" 2>/dev/null || echo 0) -gt 10000 ]; then
            RAW_FILES+=("${RAW_FILE}")
        fi
    done

    FOUND_COUNT=${#RAW_FILES[@]}
    echo "  -> Found ${FOUND_COUNT} valid raw histogram files."

    if [ "${FOUND_COUNT}" -lt "${N_EXPECTED}" ]; then
        echo "[WARNING] Expected at least ${N_EXPECTED} files, but found ${FOUND_COUNT}."
        read -p "Proceed with partial merge? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Merge aborted."
            exit 1
        fi
    fi

    echo "  -> Running hadd -f ${MERGED_ROOT} ..."
    hadd -f "${MERGED_ROOT}" "${RAW_FILES[@]}"
    echo "[STEP 3/4] Successfully merged histograms into: ${MERGED_ROOT} ($(stat -c%s "${MERGED_ROOT}" 2>/dev/null || echo 0) bytes)"
fi

# ------------------------------------------------------------------------------
# STEP 4: Perform final fits on merged statistics & output single JSON
# ------------------------------------------------------------------------------
if [ "${DO_FIT}" -eq 1 ]; then
    echo ""
    echo "[STEP 4/4] Fitting merged histograms & generating consolidated JSON..."
    if [ ! -f "${MERGED_ROOT}" ]; then
        echo "[ERROR] Merged ROOT file does not exist: ${MERGED_ROOT}" >&2
        exit 1
    fi

    CSCINT_OPT=""
    if [ -f "${CSCINT_FILE}" ]; then
        CSCINT_OPT="--cscintFile ${CSCINT_FILE}"
    fi

    if [ "${DO_FIT_SPEED}" -eq 1 ]; then
        echo "  -> Fitting full-statistics c_scint constants from merged histograms..."
        python3 -X faulthandler "${PY_RUN}" \
            -r "${RUN}" \
            --referencesystem "${REFERENCESYSTEM}" \
            --fitSpeedOnly \
            --fitOnly "${MERGED_ROOT}" \
            -o "${OUT_DIR}"
        echo ""
        echo "======================================================================"
        echo "[SUCCESS] c_scint speed extraction complete!"
        echo " Exported JSON: ${OUT_DIR}/run${RUN_STR}_cscintvalues.json"
        echo "======================================================================"
        exit 0
    fi

    python3 -X faulthandler "${PY_RUN}" \
        -r "${RUN}" \
        --referencesystem "${REFERENCESYSTEM}" \
        ${CSCINT_OPT} \
        --fitOnly "${MERGED_ROOT}" \
        -o "${OUT_DIR}"

    echo ""
    echo "======================================================================"
    echo "[SUCCESS] Pipeline Complete!"
    echo " Consolidated JSON : ${OUT_DIR}/run${RUN_STR}_timing_calibration.json"
    echo " ROOT QA & Canvases: ${OUT_DIR}/timewalk_calibration.root"
    echo "======================================================================"
fi
