#!/usr/bin/env bash
# ==============================================================================
# run_parallel_TimeWalk.sh: 10-core parallel execution of TimeWalk calibration
#
# Pipeline:
#   1. (Optional) Single-core fast pass for c_scint constants (200k events).
#   2. Parallel workers (10 jobs) running --fillOnly to accumulate 2D histograms.
#   3. hadd merges all 10 raw histogram ROOT files into a single merged file.
#   4. Single-core fast pass running --fitOnly on merged histograms to generate:
#      - timewalk_calibration.root (canvases, QA plots)
#      - run<runNr>_timing_calibration.json (consolidated calibration constants)
# ==============================================================================

set -eo pipefail

RUN="${1:-5999}"
TOTAL_EVENTS="${2:-2000000}"
N_JOBS="${3:-10}"
OUT_DIR="${4:-/eos/user/i/idioniso/Timing/run$(printf "%06d" "${RUN}")}"
REFERENCESYSTEM="${5:-0}"
SPEED_EVENTS=1000000

RUN_STR=$(printf "%06d" "${RUN}")
EVENTS_PER_JOB=$(( TOTAL_EVENTS / N_JOBS ))
CSCINT_FILE="${OUT_DIR}/run${RUN_STR}_cscintvalues.json"
CSCINT_RAW="${OUT_DIR}/raw_cscint_histograms.root"
MERGED_ROOT="${OUT_DIR}/merged_raw_histograms.root"
PARALLEL_DIR="${OUT_DIR}/parallel_parts"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
if [ -f "${SCRIPT_DIR}/run_TimeWalk.py" ]; then
    PY_RUN="${SCRIPT_DIR}/run_TimeWalk.py"
elif [ -n "$SND_HOME" ] && [ -f "$SND_HOME/sndsw/shipLHC/scripts/run_TimeWalk.py" ]; then
    PY_RUN="$SND_HOME/sndsw/shipLHC/scripts/run_TimeWalk.py"
else
    PY_RUN="/afs/cern.ch/user/i/idioniso/snd_master/sndsw/shipLHC/scripts/run_TimeWalk.py"
fi

mkdir -p "${OUT_DIR}"
mkdir -p "${PARALLEL_DIR}"

echo "======================================================================"
echo " Starting Parallel TimeWalk Calibration"
echo " Run:                 ${RUN}"
echo " Total Events:        ${TOTAL_EVENTS}"
echo " Jobs / Workers:      ${N_JOBS} (${EVENTS_PER_JOB} events each)"
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
    python -X faulthandler "${PY_RUN}" \
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
# STEP 2: Launch 10 parallel workers with --fillOnly
# ------------------------------------------------------------------------------
echo ""
echo "[STEP 2/4] Launching ${N_JOBS} parallel workers with --fillOnly..."
PIDS=()
for i in $(seq 0 $((N_JOBS - 1))); do
    START=$(( i * EVENTS_PER_JOB ))
    PART_DIR="${PARALLEL_DIR}/part_${i}"
    mkdir -p "${PART_DIR}"
    LOG_FILE="${PART_DIR}/worker_${i}.log"

    python -X faulthandler "${PY_RUN}" \
        -r "${RUN}" \
        -s "${START}" \
        -n "${EVENTS_PER_JOB}" \
        --cscintFile "${CSCINT_FILE}" \
        --referencesystem "${REFERENCESYSTEM}" \
        --fillOnly \
        -o "${PART_DIR}" > "${LOG_FILE}" 2>&1 &
    
    PID=$!
    PIDS+=("${PID}")
    echo "  -> Worker ${i} [PID ${PID}] launched: events [${START} .. $((START + EVENTS_PER_JOB))] (log: ${LOG_FILE})"
done

# Monitor and wait for all workers
FAIL=0
for i in "${!PIDS[@]}"; do
    PID="${PIDS[$i]}"
    if ! wait "${PID}"; then
        echo "[ERROR] Worker ${i} (PID ${PID}) failed! Check log: ${PARALLEL_DIR}/part_${i}/worker_${i}.log"
        FAIL=1
    fi
done

if [ ${FAIL} -ne 0 ]; then
    echo "[ABORT] One or more parallel workers failed. Aborting pipeline."
    exit 1
fi
echo "[STEP 2/4] All ${N_JOBS} workers completed successfully."

# ------------------------------------------------------------------------------
# STEP 3: Merge raw histograms across all 10 jobs with hadd
# ------------------------------------------------------------------------------
echo ""
echo "[STEP 3/4] Merging raw histograms across all ${N_JOBS} jobs with hadd..."
RAW_FILES=()
if [ -f "${CSCINT_RAW}" ]; then
    RAW_FILES+=("${CSCINT_RAW}")
fi
for i in $(seq 0 $((N_JOBS - 1))); do
    RAW_FILE=$(find "${PARALLEL_DIR}/part_${i}" -name "raw_histograms_*.root" | head -n 1)
    if [ -f "${RAW_FILE}" ]; then
        RAW_FILES+=("${RAW_FILE}")
    fi
done

if [ ${#RAW_FILES[@]} -lt ${N_JOBS} ]; then
    echo "[ERROR] Expected at least ${N_JOBS} raw histogram files, but found ${#RAW_FILES[@]}."
    exit 1
fi

hadd -f "${MERGED_ROOT}" "${RAW_FILES[@]}"
echo "[STEP 3/4] Successfully merged histograms into: ${MERGED_ROOT}"

# ------------------------------------------------------------------------------
# STEP 4: Perform final fits on merged statistics & output single JSON
# ------------------------------------------------------------------------------
echo ""
echo "[STEP 4/4] Fitting merged histograms & generating consolidated JSON..."
python -X faulthandler "${PY_RUN}" \
    -r "${RUN}" \
    --referencesystem "${REFERENCESYSTEM}" \
    --cscintFile "${CSCINT_FILE}" \
    --fitOnly "${MERGED_ROOT}" \
    -o "${OUT_DIR}"

echo ""
echo "======================================================================"
echo "[SUCCESS] Pipeline Complete!"
echo " Consolidated JSON: ${OUT_DIR}/run${RUN_STR}_timing_calibration.json"
echo " ROOT QA & Canvases: ${OUT_DIR}/timewalk_calibration.root"
echo "======================================================================"
