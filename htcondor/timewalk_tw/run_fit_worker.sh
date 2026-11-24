#!/bin/bash
set -eo pipefail

# ==============================================================================
# SND@LHC HTCondor Worker: Time-Walk Parameter Fitting per Run (Iteration 2)
#
# Arguments:
#   $1: RUN         (e.g., 5119)
#   $2: IN_DIR      (default: /eos/user/i/idioniso/Timing/timewalk_tw/runs)
#   $3: OUT_DIR     (default: /eos/user/i/idioniso/Timing/timewalk_tw/fits)
#   $4: CSCINT_DIR  (default: /eos/user/i/idioniso/Timing/cscint_tw/fits)
#   $5: OUT_ROOT_DIR(default: /eos/user/i/idioniso/Timing/timewalk_tw/fits_root)
# ==============================================================================

RUN="${1:-5119}"
IN_DIR="${2:-/eos/user/i/idioniso/Timing/timewalk_tw/runs}"
OUT_DIR="${3:-/eos/user/i/idioniso/Timing/timewalk_tw/fits}"
CSCINT_DIR="${4:-/eos/user/i/idioniso/Timing/cscint_tw/fits}"
OUT_ROOT_DIR="${5:-/eos/user/i/idioniso/Timing/timewalk_tw/fits_root}"
SAVE_CANVAS="${SAVE_CANVAS:-1}"
FORCE="${FORCE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/afs/cern.ch/work/i/idioniso/snd-veto-us"
PY_SCRIPT="${WORK_DIR}/scripts/fit_timewalk.py"

INPUT_FILE="${IN_DIR}/run${RUN}.root"
TARGET_JSON="${OUT_DIR}/run${RUN}_timing_calibration.json"
TARGET_ROOT="${OUT_ROOT_DIR}/run${RUN}.root"

echo "======================================================================"
echo " SND@LHC HTCondor Worker: Time-Walk Fitting (Iteration 2)"
echo " Host:        $(hostname)"
echo " Target:      Run ${RUN}"
echo " Input File:  ${INPUT_FILE}"
echo " Output JSON: ${TARGET_JSON}"
echo " Output ROOT: ${TARGET_ROOT}"
echo " c_scint Dir: ${CSCINT_DIR}"
echo " Save Canvas: ${SAVE_CANVAS}"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ ! -f "${INPUT_FILE}" ]; then
    echo "[ERROR] Input ROOT file does not exist: ${INPUT_FILE}" >&2
    exit 1
fi

# Skip if already fitted
if [ "${FORCE}" != "1" ] && [ -f "${TARGET_JSON}" ] && [ -f "${TARGET_ROOT}" ]; then
    JSON_SZ=$(stat -c%s "${TARGET_JSON}" 2>/dev/null || echo 0)
    ROOT_SZ=$(stat -c%s "${TARGET_ROOT}" 2>/dev/null || echo 0)
    if [ "${JSON_SZ}" -gt 10000 ] && [ "${ROOT_SZ}" -gt 1000000 ]; then
        echo "[INFO] Run ${RUN} already fitted (${JSON_SZ} B JSON, ${ROOT_SZ} B ROOT). Skipping."
        exit 0
    fi
fi

# Source sndsw environment
if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
    source "${SCRIPT_DIR}/sndswEnv.sh"
elif [ -f "${WORK_DIR}/sndswEnv.sh" ]; then
    source "${WORK_DIR}/sndswEnv.sh"
else
    echo "[ERROR] Cannot find sndswEnv.sh!" >&2
    exit 1
fi

# Scratch execution
SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/fit_timewalk_tw_${RUN}_$$"
mkdir -p "${SCRATCH_DIR}/fits_root"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

LOCAL_IN="${SCRATCH_DIR}/run${RUN}.root"
LOCAL_OUT_JSON="${SCRATCH_DIR}/run${RUN}_timing_calibration.json"
LOCAL_OUT_ROOT="${SCRATCH_DIR}/fits_root/run${RUN}.root"

echo " ~ Copying input ROOT file to local scratch..."
cp -f "${INPUT_FILE}" "${LOCAL_IN}"

CANVAS_FLAG=""
if [ "${SAVE_CANVAS}" != "1" ]; then
    CANVAS_FLAG="--no-canvas"
fi

CSCINT_OPT=""
if [ -d "${CSCINT_DIR}" ]; then
    CSCINT_OPT="--cscint-dir ${CSCINT_DIR}"
fi

echo " ~ Running fit_timewalk.py on local copy..."
python3 -X faulthandler "${PY_SCRIPT}" \
    -i "${LOCAL_IN}" \
    -o "${LOCAL_OUT_JSON}" \
    ${CSCINT_OPT} \
    ${CANVAS_FLAG} \
    --output-root-dir "${SCRATCH_DIR}/fits_root"

# Verify outputs
if [ ! -f "${LOCAL_OUT_JSON}" ]; then
    echo "[ERROR] Output JSON was not generated: ${LOCAL_OUT_JSON}" >&2
    exit 1
fi

JSON_SIZE=$(stat -c%s "${LOCAL_OUT_JSON}" 2>/dev/null || echo 0)
if [ "${JSON_SIZE}" -lt 500 ]; then
    echo "[ERROR] Generated JSON is suspiciously small (${JSON_SIZE} bytes)!" >&2
    exit 1
fi

# Transfer results back to EOS atomically
mkdir -p "${OUT_DIR}" "${OUT_ROOT_DIR}"

echo " ~ Transferring calibration JSON to ${TARGET_JSON}..."
cp -f "${LOCAL_OUT_JSON}" "${TARGET_JSON}.tmp"
mv -f "${TARGET_JSON}.tmp" "${TARGET_JSON}"

if [ -f "${LOCAL_OUT_ROOT}" ]; then
    ROOT_SIZE=$(stat -c%s "${LOCAL_OUT_ROOT}" 2>/dev/null || echo 0)
    echo " ~ Transferring updated ROOT file with canvases (${ROOT_SIZE} bytes) to ${TARGET_ROOT}..."
    cp -f "${LOCAL_OUT_ROOT}" "${TARGET_ROOT}.tmp"
    mv -f "${TARGET_ROOT}.tmp" "${TARGET_ROOT}"
fi

echo "======================================================================"
echo "[SUCCESS] Time-Walk fitting for Run ${RUN} completed successfully."
echo " Output JSON: ${TARGET_JSON} (${JSON_SIZE} bytes)"
echo " Output ROOT: ${TARGET_ROOT}"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
