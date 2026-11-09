#!/bin/bash
set -eo pipefail

# ==============================================================================
# SND@LHC HTCondor Worker Script: Single-core TimeWalk 2D Histogram Accumulation
#
# Arguments:
#   $1: JOB_ID          (0 .. 249)
#   $2: START_EVENT     (First event to process in full run chain)
#   $3: N_EVENTS        (Number of events to process in this slice)
#   $4: RUN             (Default: 5999)
#   $5: OUT_DIR         (Default: /eos/user/i/idioniso/Timing/run005999)
#   $6: REFERENCESYSTEM (Default: 0 for both DS + SciFi)
# ==============================================================================

JOB_ID="${1:-0}"
START="${2:-0}"
N_EVENTS="${3:-535150}"
RUN="${4:-5999}"
RUN_STR=$(printf "%06d" "${RUN}")
OUT_DIR="${5:-/eos/user/i/idioniso/Timing/run${RUN_STR}}"
REFERENCESYSTEM="${6:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARALLEL_DIR="${OUT_DIR}/parallel_parts"
PART_DIR="${PARALLEL_DIR}/part_${JOB_ID}"
TARGET_FILE="${PART_DIR}/raw_histograms_${START}.root"

echo "======================================================================"
echo " HTCondor TimeWalk Worker - Job ${JOB_ID}"
echo " Host:             $(hostname)"
echo " Run:              ${RUN}"
echo " Event Slice:      [${START} .. $((START + N_EVENTS))] (${N_EVENTS} events)"
echo " Reference System: ${REFERENCESYSTEM}"
echo " Destination:      ${TARGET_FILE}"
echo " Time:             $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

# Skip if target already exists and non-empty (idempotency)
if [ "${FORCE:-0}" != "1" ] && [ -f "${TARGET_FILE}" ]; then
    FILE_SIZE=$(stat -c%s "${TARGET_FILE}" 2>/dev/null || echo 0)
    if [ "${FILE_SIZE}" -gt 10000 ]; then
        echo "[SKIP] Output ${TARGET_FILE} already exists (${FILE_SIZE} bytes) and FORCE!=1. Exiting cleanly."
        exit 0
    fi
fi

# 1. Source Environment
if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
    echo " ~ Sourcing environment: ${SCRIPT_DIR}/sndswEnv.sh"
    source "${SCRIPT_DIR}/sndswEnv.sh"
elif [ -f "/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/setUp.sh" ]; then
    echo " ~ Sourcing fallback: /cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/setUp.sh"
    source "/cvmfs/sndlhc.cern.ch/SNDLHC-2025/Oct7/setUp.sh"
fi

# Setup ddfUtils
if [ -d "${SCRIPT_DIR}/ddfUtils" ]; then
    export ddfUtils="${SCRIPT_DIR}/ddfUtils"
elif [ -d "/afs/cern.ch/user/i/idioniso/ddfUtils" ]; then
    export ddfUtils="/afs/cern.ch/user/i/idioniso/ddfUtils"
fi
export PYTHONPATH="${ddfUtils}:${PYTHONPATH+:$PYTHONPATH}"

# 2. Locate Runner Script
PY_RUN="/afs/cern.ch/user/i/idioniso/snd_master/sndsw/shipLHC/scripts/run_TimeWalk.py"
if [ ! -f "${PY_RUN}" ]; then
    PY_RUN="${USER_SNDSW_SRC}/shipLHC/scripts/run_TimeWalk.py"
fi

if [ ! -f "${PY_RUN}" ]; then
    echo "[ERROR] Cannot find run_TimeWalk.py at ${PY_RUN}." >&2
    exit 1
fi

# 3. Check for c_scint speed calibration file
CSCINT_FILE="${OUT_DIR}/run${RUN_STR}_cscintvalues.json"
CSCINT_OPT=""
if [ -f "${CSCINT_FILE}" ]; then
    echo " ~ Using precomputed c_scint file: ${CSCINT_FILE}"
    CSCINT_OPT="--cscintFile ${CSCINT_FILE}"
else
    echo " ~ [WARNING] No precomputed c_scint file found at ${CSCINT_FILE}."
fi

# 4. Local scratch directory for fast I/O
SCRATCH_DIR=$(mktemp -d /tmp/tw_part_${JOB_ID}_XXXXXX)
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

echo " ~ Running run_TimeWalk.py in local scratch: ${SCRATCH_DIR}"

python3 -X faulthandler "${PY_RUN}" \
    -r "${RUN}" \
    -s "${START}" \
    -n "${N_EVENTS}" \
    ${CSCINT_OPT} \
    --referencesystem "${REFERENCESYSTEM}" \
    --fillOnly \
    -o "${SCRATCH_DIR}"

# 5. Verify generated raw histogram ROOT file
PROD_FILE=$(find "${SCRATCH_DIR}" -name "raw_histograms_*.root" | head -n 1)

if [ -z "${PROD_FILE}" ] || [ ! -f "${PROD_FILE}" ]; then
    echo "[ERROR] No raw_histograms_*.root found in ${SCRATCH_DIR}!" >&2
    exit 1
fi

PROD_SIZE=$(stat -c%s "${PROD_FILE}" 2>/dev/null || echo 0)
if [ "${PROD_SIZE}" -lt 5000 ]; then
    echo "[ERROR] Output file ${PROD_FILE} is suspiciously small (${PROD_SIZE} bytes)." >&2
    exit 1
fi

# 6. Copy output to final EOS destination
mkdir -p "${PART_DIR}"
cp -f "${PROD_FILE}" "${TARGET_FILE}"

echo "======================================================================"
echo "[SUCCESS] Job ${JOB_ID} finished successfully."
echo " Saved output to: ${TARGET_FILE} (${PROD_SIZE} bytes)"
echo " Time:            $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
