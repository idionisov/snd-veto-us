#!/usr/bin/env bash
# ==============================================================================
# run_TimeWalk.sh: 250-node HTCondor Distributed Execution of TimeWalk Calibration
#
# Pipeline:
#   1. (Step 1) Single-core fast pass for c_scint constants (1M events).
#   2. (Step 2) 250 parallel single-threaded HTCondor worker nodes running
#               run_TimeWalk_worker.sh with --fillOnly across the 133.8M events.
#   3. (Step 3) hadd merges all 250 raw histogram ROOT files into a single file.
#   4. (Step 4) Single-core fast pass running --fitOnly on merged histograms:
#      - timewalk_calibration.root (canvases, QA plots)
#      - run005999_timing_calibration.json (consolidated calibration constants)
# ==============================================================================

set -eo pipefail

RUN="${1:-5999}"
RUN_STR=$(printf "%06d" "${RUN}")
OUT_DIR="/eos/user/i/idioniso/Timing/run${RUN_STR}"
REFERENCESYSTEM="0"
SPEED_EVENTS="${SPEED_EVENTS:-2000000}"

CSCINT_FILE="${OUT_DIR}/run${RUN_STR}_cscintvalues.json"
CSCINT_RAW="${OUT_DIR}/raw_cscint_histograms.root"
MERGED_ROOT="${OUT_DIR}/merged_raw_histograms.root"
PARALLEL_DIR="${OUT_DIR}/parallel_parts"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_RUN="/afs/cern.ch/user/i/idioniso/snd_master/sndsw/shipLHC/scripts/run_TimeWalk.py"

mkdir -p "${OUT_DIR}"
mkdir -p "${PARALLEL_DIR}"

# Handle subcommands
case "$1" in
    --status)
        "${SCRIPT_DIR}/status_pExtr.sh" "${RUN}" "${OUT_DIR}"
        exit 0
        ;;
    --merge)
        "${SCRIPT_DIR}/merge_and_fit.sh" "${RUN}" --merge
        exit 0
        ;;
    --fit)
        "${SCRIPT_DIR}/merge_and_fit.sh" "${RUN}" --fit
        exit 0
        ;;
    --merge-fit)
        "${SCRIPT_DIR}/merge_and_fit.sh" "${RUN}"
        exit 0
        ;;
esac

echo "======================================================================"
echo " Starting Distributed TimeWalk Calibration (250 HTCondor Jobs)"
echo " Run:                 ${RUN}"
echo " Reference System:    ${REFERENCESYSTEM} (0 = DS + SF)"
echo " Output Directory:    ${OUT_DIR}"
echo " Runner Script:       ${PY_RUN}"
echo "======================================================================"

# ------------------------------------------------------------------------------
# STEP 1: Ensure c_scint speed constants exist
# ------------------------------------------------------------------------------
if [ ! -f "${CSCINT_FILE}" ] || [ ! -f "${CSCINT_RAW}" ]; then
    echo ""
    echo "[STEP 1/4] Extracting c_scint speed constants (${SPEED_EVENTS} events, 1 core)..."
    if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
        source "${SCRIPT_DIR}/sndswEnv.sh"
    fi
    python3 -X faulthandler "${PY_RUN}" \
        -r "${RUN}" \
        -s 0 \
        -n "${SPEED_EVENTS}" \
        --speedEvents "${SPEED_EVENTS}" \
        --speedOnly \
        --referencesystem "${REFERENCESYSTEM}" \
        -o "${OUT_DIR}"
    echo "[STEP 1/4] c_scint extraction completed: ${CSCINT_FILE}"
else
    echo ""
    echo "[STEP 1/4] Using pre-existing c_scint file: ${CSCINT_FILE}"
fi

# ------------------------------------------------------------------------------
# STEP 2: Submit 250 parallel single-threaded workers to HTCondor
# ------------------------------------------------------------------------------
echo ""
echo "[STEP 2/4] Submitting 250 parallel worker jobs to HTCondor..."
"${SCRIPT_DIR}/submit_pExtr.sh" --run "${RUN}" --out-dir "${OUT_DIR}"

echo ""
echo "======================================================================"
echo " 250 HTCondor jobs queued."
echo " - Monitor progress with: ./status_pExtr.sh"
echo " - Once complete, run:    ./merge_and_fit.sh"
echo "======================================================================"
