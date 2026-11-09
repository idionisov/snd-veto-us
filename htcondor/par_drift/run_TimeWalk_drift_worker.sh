#!/bin/bash
set -eo pipefail

# ==============================================================================
# SND@LHC HTCondor Worker Script: Single-run TimeWalk Drift Calibration
#
# Arguments:
#   $1: RUN             (Run number)
#   $2: N_EVENTS        (Number of events for TimeWalk fit, default: 10000000)
#   $3: OUT_BASE        (Base output directory, default: /eos/user/i/idioniso/Timing)
#   $4: REFERENCESYSTEM (Reference system, default: 0 for both DS + SciFi)
#   $5: SPEED_EVENTS    (Number of events for c_scint extraction, default: 10000000)
# ==============================================================================

RUN="${1}"
if [ -z "${RUN}" ]; then
    echo "[ERROR] Missing required RUN argument." >&2
    exit 1
fi

N_EVENTS="${2:-10000000}"
OUT_BASE="${3:-/eos/user/i/idioniso/Timing}"
REFERENCESYSTEM="${4:-0}"
SPEED_EVENTS="${5:-${N_EVENTS}}"

RUN_STR=$(printf "%06d" "${RUN}")
OUT_DIR="${OUT_BASE}/run${RUN_STR}"
FINAL_JSON="${OUT_DIR}/run${RUN_STR}_timing_calibration.json"
FINAL_ROOT="${OUT_DIR}/timewalk_calibration.root"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo " HTCondor TimeWalk Drift Worker - Run ${RUN}"
echo " Host:             $(hostname)"
echo " Run Number:       ${RUN}"
echo " Max Events:       ${N_EVENTS}"
echo " Reference System: ${REFERENCESYSTEM}"
echo " Destination:      ${OUT_DIR}"
echo " Time:             $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

# Skip if outputs already exist and are valid (idempotency)
if [ "${FORCE:-0}" != "1" ] && [ -f "${FINAL_JSON}" ] && [ -f "${FINAL_ROOT}" ]; then
    ROOT_SIZE=$(stat -c%s "${FINAL_ROOT}" 2>/dev/null || echo 0)
    JSON_SIZE=$(stat -c%s "${FINAL_JSON}" 2>/dev/null || echo 0)
    if [ "${ROOT_SIZE}" -gt 50000 ] && [ "${JSON_SIZE}" -gt 1000 ]; then
        echo "[SKIP] Outputs for run ${RUN} already exist (${ROOT_SIZE} and ${JSON_SIZE} bytes) and FORCE!=1. Exiting cleanly."
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

# 3. Local scratch directory for fast I/O
SCRATCH_DIR=$(mktemp -d /tmp/tw_drift_${RUN}_XXXXXX)
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

echo " ~ Running run_TimeWalk.py in local scratch: ${SCRATCH_DIR}"

python3 -X faulthandler "${PY_RUN}" \
    -r "${RUN}" \
    -s 0 \
    -n "${N_EVENTS}" \
    --speedEvents "${SPEED_EVENTS}" \
    --referencesystem "${REFERENCESYSTEM}" \
    -o "${SCRATCH_DIR}"

# 4. Verify generated outputs
PROD_JSON=$(find "${SCRATCH_DIR}" -name "*timing_calibration.json" | head -n 1)
PROD_ROOT=$(find "${SCRATCH_DIR}" -name "timewalk_calibration.root" | head -n 1)

if [ -z "${PROD_JSON}" ] || [ ! -f "${PROD_JSON}" ]; then
    echo "[ERROR] Calibration JSON was not created in ${SCRATCH_DIR}!" >&2
    exit 1
fi

if [ -z "${PROD_ROOT}" ] || [ ! -f "${PROD_ROOT}" ]; then
    echo "[ERROR] timewalk_calibration.root was not created in ${SCRATCH_DIR}!" >&2
    exit 1
fi

# 5. Copy outputs to destination on EOS
mkdir -p "${OUT_DIR}"
cp -f "${SCRATCH_DIR}"/* "${OUT_DIR}/"

echo "======================================================================"
echo "[SUCCESS] Run ${RUN} completed successfully."
echo " Outputs saved to: ${OUT_DIR}"
echo " Time:             $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
