#!/bin/bash
set -eo pipefail

# ==============================================================================
# SND@LHC HTCondor Worker: Time-Walk Parameter Fitting per Run
#
# Arguments:
#   $1: RUN         (e.g., 5119 or catII)
#   $2: IN_DIR      (default: /eos/user/i/idioniso/Timing/timewalk/runs)
#   $3: OUT_DIR     (default: /eos/user/i/idioniso/Timing/timewalk/fits)
#   $4: CSCINT_DIR  (default: /eos/user/i/idioniso/Timing/cscint/fits)
# ==============================================================================

RUN="${1:-5119}"
IN_DIR="${2:-/eos/user/i/idioniso/Timing/timewalk/runs}"
OUT_DIR="${3:-/eos/user/i/idioniso/Timing/timewalk/fits}"
CSCINT_DIR="${4:-/eos/user/i/idioniso/Timing/cscint/fits}"
SAVE_CANVAS="${SAVE_CANVAS:-1}"
FORCE="${FORCE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK_DIR="/afs/cern.ch/work/i/idioniso/snd-veto-us"
PY_SCRIPT="${WORK_DIR}/scripts/fit_timewalk.py"

# 1. Resolve Input File
INPUT_FILE=""
if [[ "${RUN}" =~ ^cat[I|V|X]+$ ]]; then
    # Category file
    if [ -f "${IN_DIR}/../categories/${RUN}.root" ]; then
        INPUT_FILE="${IN_DIR}/../categories/${RUN}.root"
    elif [ -f "${IN_DIR}/${RUN}.root" ]; then
        INPUT_FILE="${IN_DIR}/${RUN}.root"
    fi
    TARGET_JSON="${OUT_DIR}/${RUN}_timing_calibration.json"
else
    # Run file
    if [ -f "${IN_DIR}/run${RUN}.root" ]; then
        INPUT_FILE="${IN_DIR}/run${RUN}.root"
    elif [ -f "${IN_DIR}/${RUN}.root" ]; then
        INPUT_FILE="${IN_DIR}/${RUN}.root"
    fi
    TARGET_JSON="${OUT_DIR}/run${RUN}_timing_calibration.json"
fi

echo "======================================================================"
echo " SND@LHC HTCondor Worker: Time-Walk Fitting"
echo " Host:        $(hostname)"
echo " Target:      Run ${RUN}"
echo " Input File:  ${INPUT_FILE}"
echo " Output JSON: ${TARGET_JSON}"
echo " c_scint Dir: ${CSCINT_DIR}"
echo " Save Canvas: ${SAVE_CANVAS}"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ -z "${INPUT_FILE}" ] || [ ! -f "${INPUT_FILE}" ]; then
    echo "[ERROR] Input ROOT file does not exist: ${IN_DIR}/run${RUN}.root" >&2
    exit 1
fi

# 2. Skip if already fitted and non-empty (unless FORCE=1)
if [ "${FORCE}" != "1" ] && [ -f "${TARGET_JSON}" ]; then
    JSON_SIZE=$(stat -c%s "${TARGET_JSON}" 2>/dev/null || echo 0)
    if [ "${JSON_SIZE}" -gt 1000 ]; then
        echo "[INFO] Calibration JSON ${TARGET_JSON} already exists (${JSON_SIZE} bytes). Skipping."
        exit 0
    fi
fi

# 3. Source environment
if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
    source "${SCRIPT_DIR}/sndswEnv.sh"
elif [ -f "${WORK_DIR}/sndswEnv.sh" ]; then
    source "${WORK_DIR}/sndswEnv.sh"
else
    echo "[ERROR] Cannot find sndswEnv.sh!" >&2
    exit 1
fi

# 4. Local scratch setup
SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/fit_tw_${RUN}_$$"
mkdir -p "${SCRATCH_DIR}"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

LOCAL_IN="${SCRATCH_DIR}/$(basename "${INPUT_FILE}")"
LOCAL_OUT_JSON="${SCRATCH_DIR}/output_calibration.json"

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
    ${CANVAS_FLAG}

# 5. Verify output
if [ ! -f "${LOCAL_OUT_JSON}" ]; then
    echo "[ERROR] Output JSON was not generated: ${LOCAL_OUT_JSON}" >&2
    exit 1
fi

JSON_SIZE=$(stat -c%s "${LOCAL_OUT_JSON}" 2>/dev/null || echo 0)
if [ "${JSON_SIZE}" -lt 500 ]; then
    echo "[ERROR] Generated JSON is suspiciously small (${JSON_SIZE} bytes)!" >&2
    exit 1
fi

# 6. Copy results back to EOS atomically
mkdir -p "${OUT_DIR}"
echo " ~ Transferring calibration JSON to ${TARGET_JSON}..."
cp -f "${LOCAL_OUT_JSON}" "${TARGET_JSON}.tmp"
mv -f "${TARGET_JSON}.tmp" "${TARGET_JSON}"

if [ "${SAVE_CANVAS}" == "1" ]; then
    echo " ~ Updating ROOT file with fit canvases on EOS..."
    cp -f "${LOCAL_IN}" "${INPUT_FILE}.tmp"
    mv -f "${INPUT_FILE}.tmp" "${INPUT_FILE}"
fi

echo "======================================================================"
echo "[SUCCESS] Time-Walk fitting for Run ${RUN} completed successfully."
echo " Output saved to: ${TARGET_JSON} (${JSON_SIZE} bytes)"
echo " Time:            $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
