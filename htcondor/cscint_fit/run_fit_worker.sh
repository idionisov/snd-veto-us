#!/bin/bash
set -eo pipefail

# ==============================================================================
# HTCondor Worker: Time-Walk Parameter Fitting per Run
#
# Arguments:
#   $1: RUN          (e.g., 5119)
#   $2: IN_DIR       (default: /eos/user/i/idioniso/Timing/timewalk/runs)
#   $3: OUT_DIR      (default: /eos/user/i/idioniso/Timing/timewalk/fits)
#   $4: CSCINT_DIR   (default: /eos/user/i/idioniso/Timing/cscint/fits)
#   $5: OUT_ROOT_DIR (default: /eos/user/i/idioniso/Timing/timewalk/fits_root)
# ==============================================================================

RUN="${1:-5119}"
IN_DIR="${2:-/eos/user/i/idioniso/Timing/timewalk/runs}"
OUT_DIR="${3:-/eos/user/i/idioniso/Timing/timewalk/fits}"
CSCINT_DIR="${4:-/eos/user/i/idioniso/Timing/cscint/fits}"
OUT_ROOT_DIR="${5:-/eos/user/i/idioniso/Timing/timewalk/fits_root}"
FORCE="${FORCE:-0}"

WORK_DIR="/afs/cern.ch/work/i/idioniso/snd-veto-us"
PY_SCRIPT="${WORK_DIR}/scripts/fit_timewalk.py"

IN_FILE="${IN_DIR}/run${RUN}.root"
TARGET_JSON="${OUT_DIR}/run${RUN}_timing_calibration.json"
TARGET_ROOT="${OUT_ROOT_DIR}/run${RUN}.root"

echo "======================================================================"
echo " SND@LHC HTCondor Worker: Time-Walk Fit (cscint_fit)"
echo " Host:           $(hostname)"
echo " Run:            ${RUN}"
echo " Input File:     ${IN_FILE}"
echo " Output JSON:    ${TARGET_JSON}"
echo " Output ROOT:    ${TARGET_ROOT}"
echo " c_scint Dir:    ${CSCINT_DIR}"
echo " Force Overwrite: ${FORCE}"
echo " Start Time:     $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

# 1. Validate Input
if [ ! -f "${IN_FILE}" ]; then
    echo "[ERROR] Input ROOT file not found: ${IN_FILE}" >&2
    exit 1
fi

# 2. Check if already fitted
if [ "${FORCE}" != "1" ] && [ -f "${TARGET_JSON}" ] && [ -f "${TARGET_ROOT}" ]; then
    JSON_SZ=$(stat -c%s "${TARGET_JSON}" 2>/dev/null || echo 0)
    ROOT_SZ=$(stat -c%s "${TARGET_ROOT}" 2>/dev/null || echo 0)
    if [ "${JSON_SZ}" -gt 1000 ] && [ "${ROOT_SZ}" -gt 1000000 ]; then
        echo "[INFO] Run ${RUN} already fitted (JSON: ${JSON_SZ} B, ROOT: ${ROOT_SZ} B). Skipping."
        exit 0
    fi
fi

# 3. Source environment
if [ -f "${WORK_DIR}/sndswEnv.sh" ]; then
    source "${WORK_DIR}/sndswEnv.sh"
else
    echo "[ERROR] sndswEnv.sh not found at ${WORK_DIR}!" >&2
    exit 1
fi

# 4. Local scratch execution
SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/fit_cscint_${RUN}_$$"
mkdir -p "${SCRATCH_DIR}/fits_root"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

LOCAL_IN="${SCRATCH_DIR}/run${RUN}.root"
LOCAL_OUT_JSON="${SCRATCH_DIR}/run${RUN}_timing_calibration.json"
LOCAL_OUT_ROOT="${SCRATCH_DIR}/fits_root/run${RUN}.root"

echo " ~ Copying input ROOT file to local scratch..."
cp -f "${IN_FILE}" "${LOCAL_IN}"

CSCINT_OPT=""
if [ -d "${CSCINT_DIR}" ]; then
    CSCINT_OPT="--cscint-dir ${CSCINT_DIR}"
fi

echo " ~ Running fit_timewalk.py on Run ${RUN}..."
python3 -X faulthandler "${PY_SCRIPT}" \
    -i "${LOCAL_IN}" \
    -o "${LOCAL_OUT_JSON}" \
    ${CSCINT_OPT} \
    --output-root-dir "${SCRATCH_DIR}/fits_root"

# 5. Verify outputs
if [ ! -f "${LOCAL_OUT_JSON}" ]; then
    echo "[ERROR] Expected JSON output not found: ${LOCAL_OUT_JSON}" >&2
    exit 1
fi

if [ ! -f "${LOCAL_OUT_ROOT}" ]; then
    echo "[ERROR] Expected ROOT output not found: ${LOCAL_OUT_ROOT}" >&2
    exit 1
fi

JSON_SZ=$(stat -c%s "${LOCAL_OUT_JSON}" 2>/dev/null || echo 0)
ROOT_SZ=$(stat -c%s "${LOCAL_OUT_ROOT}" 2>/dev/null || echo 0)

if [ "${JSON_SZ}" -lt 500 ]; then
    echo "[ERROR] Output JSON is suspiciously small (${JSON_SZ} B)!" >&2
    exit 1
fi

# 6. Copy back to EOS atomically
mkdir -p "${OUT_DIR}" "${OUT_ROOT_DIR}"

echo " ~ Transferring output JSON to ${TARGET_JSON}..."
cp -f "${LOCAL_OUT_JSON}" "${TARGET_JSON}.tmp"
mv -f "${TARGET_JSON}.tmp" "${TARGET_JSON}"

echo " ~ Transferring output ROOT to ${TARGET_ROOT}..."
cp -f "${LOCAL_OUT_ROOT}" "${TARGET_ROOT}.tmp"
mv -f "${TARGET_ROOT}.tmp" "${TARGET_ROOT}"

echo "======================================================================"
echo "[SUCCESS] Run ${RUN} completed successfully."
echo " Saved JSON: ${TARGET_JSON} (${JSON_SZ} bytes)"
echo " Saved ROOT: ${TARGET_ROOT} (${ROOT_SZ} bytes)"
echo " End Time:   $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
