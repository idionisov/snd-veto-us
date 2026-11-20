#!/bin/bash
set -eo pipefail

# ==============================================================================
# SND@LHC HTCondor Worker: SciFi-DS Inter-System Shift Extraction per Partition
#
# Arguments:
#   $1: RUN        (e.g., 5119)
#   $2: PARTITION  (e.g., 0)
#   $3: CATEGORY   (e.g., catII or catIII)
#   $4: OUT_BASE   (default: /eos/user/i/idioniso/Timing/interSystemShift_parts)
# ==============================================================================

RUN="${1:-5119}"
PARTITION="${2:-0}"
CATEGORY="${3:-catII}"
OUT_BASE="${4:-/eos/user/i/idioniso/Timing/interSystemShift_parts}"
FORCE="${FORCE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${OUT_BASE}/${CATEGORY}/run${RUN}"
TARGET_FILE="${TARGET_DIR}/part_${PARTITION}.root"

echo "======================================================================"
echo " SND@LHC HTCondor Worker: Inter-System Time Shift"
echo " Host:        $(hostname)"
echo " Run:         ${RUN}"
echo " Partition:   ${PARTITION}"
echo " Category:    ${CATEGORY}"
echo " Destination: ${TARGET_FILE}"
echo " Flavour:     workday"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

# 1. Skip if already processed and valid
if [ "${FORCE}" != "1" ] && [ -f "${TARGET_FILE}" ]; then
    FILE_SIZE=$(stat -c%s "${TARGET_FILE}" 2>/dev/null || echo 0)
    if [ "${FILE_SIZE}" -gt 2000 ]; then
        echo "[INFO] Target file ${TARGET_FILE} already exists (${FILE_SIZE} bytes). Skipping."
        exit 0
    fi
fi

# 2. Source sndsw environment
if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
    source "${SCRIPT_DIR}/sndswEnv.sh"
elif [ -f "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh" ]; then
    source "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh"
else
    echo "[ERROR] Cannot find sndswEnv.sh!" >&2
    exit 1
fi

# 3. Create local scratch space
SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/shift_${RUN}_part${PARTITION}_$$"
mkdir -p "${SCRATCH_DIR}"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

TEMP_OUT="${SCRATCH_DIR}/part_${PARTITION}.root"
PY_SCRIPT="/afs/cern.ch/work/i/idioniso/snd-veto-us/scripts/event_ref_time.py"
WINDOWS_JSON="/afs/cern.ch/work/i/idioniso/snd-veto-us/config/ref_time_windows.json"

echo " ~ Processing partition ${PARTITION} of run ${RUN} in scratch: ${SCRATCH_DIR}"

python3 -X faulthandler "${PY_SCRIPT}" \
    --worker \
    -r "${RUN}" \
    -P "${PARTITION}" \
    -n 0 \
    -c "${CATEGORY}" \
    --windows-json "${WINDOWS_JSON}" \
    -o "${TEMP_OUT}"

# 4. Verify output file
if [ ! -f "${TEMP_OUT}" ]; then
    echo "[ERROR] Output file was not generated: ${TEMP_OUT}" >&2
    exit 1
fi

PROD_SIZE=$(stat -c%s "${TEMP_OUT}" 2>/dev/null || echo 0)
if [ "${PROD_SIZE}" -lt 1000 ]; then
    echo "[ERROR] Generated output file ${TEMP_OUT} is suspiciously small (${PROD_SIZE} bytes)!" >&2
    exit 1
fi

# 5. Atomic copy to EOS
mkdir -p "${TARGET_DIR}"
cp -f "${TEMP_OUT}" "${TARGET_FILE}.tmp"
mv -f "${TARGET_FILE}.tmp" "${TARGET_FILE}"

# Also copy JSON metadata if generated
TEMP_JSON="${SCRATCH_DIR}/part_${PARTITION}.json"
TARGET_JSON="${TARGET_DIR}/part_${PARTITION}.json"
if [ -f "${TEMP_JSON}" ]; then
    cp -f "${TEMP_JSON}" "${TARGET_JSON}.tmp"
    mv -f "${TARGET_JSON}.tmp" "${TARGET_JSON}"
fi

echo "======================================================================"
echo "[SUCCESS] Partition ${PARTITION} of Run ${RUN} completed."
echo " Output saved to: ${TARGET_FILE} (${PROD_SIZE} bytes)"
echo " Time:            $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
