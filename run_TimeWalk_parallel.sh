#!/bin/bash
set -euo pipefail

# Source environment
source /afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh

# Parse CLI arguments (defaults: 5M events per stage, 10 threads)
RUN=${1:-5100}
N_EVENTS_STAGE1=${2:-5000000}
N_EVENTS_STAGE2=${3:-5000000}
N_THREADS=${4:-10}
OUT_BASE=${5:-"/eos/user/i/idioniso/Timing"}

RUN_FORMATTED=$(printf "%06d" "${RUN}")
SNDSW_DIR="/afs/cern.ch/user/i/idioniso/snd_master/sndsw"
PY_SCRIPT="${SNDSW_DIR}/shipLHC/scripts/run_TimeWalk.py"
OUT_DIR="${OUT_BASE}/run${RUN}"
PART_DIR="${OUT_DIR}/parallel_tmp"

mkdir -p "${PART_DIR}"

EVENTS_PER_JOB_STAGE1=$(( (N_EVENTS_STAGE1 + N_THREADS - 1) / N_THREADS ))
EVENTS_PER_JOB_STAGE2=$(( (N_EVENTS_STAGE2 + N_THREADS - 1) / N_THREADS ))

echo "=== Starting Stage 1: cscint histogram extraction (${N_THREADS} threads, ${N_EVENTS_STAGE1} events) ==="
pids=()
for ((i=0; i<N_THREADS; i++)); do
    START_EVT=$(( i * EVENTS_PER_JOB_STAGE1 ))
    JOB_DIR="${PART_DIR}/stage1_part_${i}"
    mkdir -p "${JOB_DIR}"
    python3 -X faulthandler "${PY_SCRIPT}" -r "${RUN}" -s "${START_EVT}" -n "${EVENTS_PER_JOB_STAGE1}" \
        --speedOnly --fillOnly -o "${JOB_DIR}" > "${JOB_DIR}/job.log" 2>&1 &
    pids+=($!)
done

# Wait for Stage 1 jobs
for pid in "${pids[@]}"; do
    wait "${pid}"
done
echo "=== Stage 1 histogram accumulation completed successfully ==="

# Merge Stage 1 raw histograms
STAGE1_MERGED="${OUT_DIR}/merged_raw_cscint.root"
echo "Merging Stage 1 histograms into ${STAGE1_MERGED}..."
rm -f "${STAGE1_MERGED}"
hadd -f -k "${STAGE1_MERGED}" "${PART_DIR}"/stage1_part_*/raw_*.root > /dev/null

# Fit Stage 1 merged histograms
echo "Fitting Stage 1 merged histograms to extract cscint..."
python3 -X faulthandler "${PY_SCRIPT}" -r "${RUN}" --fitSpeedOnly --fitOnly "${STAGE1_MERGED}" -o "${OUT_DIR}"

CSCINT_JSON="${OUT_DIR}/run${RUN_FORMATTED}_cscintvalues.json"
if [ ! -f "${CSCINT_JSON}" ]; then
    CSCINT_JSON="${OUT_DIR}/run${RUN}_cscintvalues.json"
fi

if [ ! -f "${CSCINT_JSON}" ]; then
    echo "ERROR: cscint JSON was not generated at expected locations!" >&2
    exit 1
fi
echo "=== Stage 1 complete. Extracted: ${CSCINT_JSON} ==="

# Stage 2: TimeWalk histogram accumulation
echo "=== Starting Stage 2: TimeWalk histogram accumulation (${N_THREADS} threads, ${N_EVENTS_STAGE2} events) ==="
pids=()
STAGE2_BASE_OFFSET="${N_EVENTS_STAGE1}"
for ((i=0; i<N_THREADS; i++)); do
    START_EVT=$(( STAGE2_BASE_OFFSET + i * EVENTS_PER_JOB_STAGE2 ))
    JOB_DIR="${PART_DIR}/stage2_part_${i}"
    mkdir -p "${JOB_DIR}"
    python3 -X faulthandler "${PY_SCRIPT}" -r "${RUN}" -s "${START_EVT}" -n "${EVENTS_PER_JOB_STAGE2}" \
        --fillOnly --cscintFile "${CSCINT_JSON}" -o "${JOB_DIR}" > "${JOB_DIR}/job.log" 2>&1 &
    pids+=($!)
done

# Wait for Stage 2 jobs
for pid in "${pids[@]}"; do
    wait "${pid}"
done
echo "=== Stage 2 histogram accumulation completed successfully ==="

# Merge Stage 2 raw histograms
STAGE2_MERGED="${OUT_DIR}/merged_raw_histograms.root"
echo "Merging Stage 2 histograms into ${STAGE2_MERGED}..."
rm -f "${STAGE2_MERGED}"
hadd -f -k "${STAGE2_MERGED}" "${PART_DIR}"/stage2_part_*/raw_*.root > /dev/null

# Fit Stage 2 merged histograms
echo "Fitting Stage 2 merged histograms to extract timewalk + alignment parameters..."
python3 -X faulthandler "${PY_SCRIPT}" -r "${RUN}" --cscintFile "${CSCINT_JSON}" --fitOnly "${STAGE2_MERGED}" -o "${OUT_DIR}"

CALIB_JSON="${OUT_DIR}/run${RUN_FORMATTED}_timing_calibration.json"
if [ ! -f "${CALIB_JSON}" ]; then
    CALIB_JSON="${OUT_DIR}/run${RUN}_timing_calibration.json"
fi

echo "=== Pipeline completed successfully for Run ${RUN} ==="
echo "Final calibration output: ${CALIB_JSON}"
