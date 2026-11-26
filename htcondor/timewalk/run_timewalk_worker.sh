#!/bin/bash
set -eo pipefail

# ==============================================================================
# SND@LHC HTCondor Worker: Time-Walk Extraction per Partition
#
# Arguments:
#   $1: RUN         (e.g., 5119)
#   $2: PARTITION   (e.g., 0)
#   $3: CATEGORY    (e.g., catII)
#   $4: OUT_BASE    (default: /eos/user/i/idioniso/Timing/timewalk_parts)
#   $5: CSCINT_DIR  (default: /eos/user/i/idioniso/Timing/cscint/fits)
#   $6: CSCINT_FILE (optional explicit path to c_scint JSON file)
# ==============================================================================

RUN="${1:-5119}"
PARTITION="${2:-0}"
CATEGORY="${3:-catII}"
OUT_BASE="${4:-/eos/user/i/idioniso/Timing/timewalk2/parts}"
CSCINT_DIR="${5:-/eos/user/i/idioniso/Timing/cscint/fits}"
SUBSYSTEM_CSCINT="${6:-/afs/cern.ch/work/i/idioniso/snd-veto-us/config/subsystem_cscint.json}"
FORCE="${FORCE:-0}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${OUT_BASE}/${CATEGORY}/run${RUN}"
TARGET_FILE="${TARGET_DIR}/part_${PARTITION}.root"

mkdir -p "${TARGET_DIR}" "${SCRIPT_DIR}/out" "${SCRIPT_DIR}/err" "${SCRIPT_DIR}/log"

echo "======================================================================"
echo " SND@LHC HTCondor Worker: Time-Walk (ToF Corrected dt vs QDC)"
echo " Host:        $(hostname)"
echo " Run:         ${RUN}"
echo " Partition:   ${PARTITION}"
echo " Category:    ${CATEGORY}"
echo " Destination: ${TARGET_FILE}"
echo " c_scint Dir: ${CSCINT_DIR}"
echo " Unified cfg: ${SUBSYSTEM_CSCINT}"
echo " Flavour:     workday"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

# 1. Skip if already processed
if [ "${FORCE}" != "1" ] && [ -f "${TARGET_FILE}" ]; then
    FILE_SIZE=$(stat -c%s "${TARGET_FILE}" 2>/dev/null || echo 0)
    if [ "${FILE_SIZE}" -gt 1000 ]; then
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

# 3. Resolve individual and subsystem c_scint constants
RUN_PADDED=$(printf "%06d" "${RUN}")
FOUND_FILE=""
for cand in \
    "${CSCINT_DIR}/run${RUN}_cscint.json" \
    "${CSCINT_DIR}/run${RUN_PADDED}_cscint.json" \
    "${CSCINT_DIR}/run_${RUN}_cscint.json" \
    "${CSCINT_DIR}/run${RUN}.json"; do
    if [ -f "${cand}" ]; then
        FOUND_FILE="${cand}"
        break
    fi
done

CSCINT_OPT=""
if [ -n "${FOUND_FILE}" ]; then
    CSCINT_OPT="--cscint-file ${FOUND_FILE}"
    echo "[INFO] Individual SiPM c_scint constants: ${FOUND_FILE}"
elif [ -d "${CSCINT_DIR}" ]; then
    CSCINT_OPT="--cscint-dir ${CSCINT_DIR}"
    echo "[INFO] Individual SiPM c_scint directory: ${CSCINT_DIR}"
else
    echo "[WARNING] Individual c_scint directory ${CSCINT_DIR} not found; falling back to subsystem constants."
fi

SUBSYS_OPT=""
if [ -f "${SUBSYSTEM_CSCINT}" ]; then
    SUBSYS_OPT="--subsystem-cscint ${SUBSYSTEM_CSCINT}"
    echo "[INFO] Subsystem unified c_scint constants: ${SUBSYSTEM_CSCINT}"
fi

# 4. Create local scratch space
SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/timewalk_${RUN}_part${PARTITION}_$$"
mkdir -p "${SCRATCH_DIR}"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

TEMP_OUT="${SCRATCH_DIR}/part_${PARTITION}.root"
PY_SCRIPT="/afs/cern.ch/work/i/idioniso/snd-veto-us/scripts/timewalk.py"
WINDOWS_JSON="/afs/cern.ch/work/i/idioniso/snd-veto-us/config/ref_time_windows.json"

echo " ~ Processing partition ${PARTITION} of run ${RUN} in scratch: ${SCRATCH_DIR}"

python3 -X faulthandler "${PY_SCRIPT}" \
    --worker \
    -r "${RUN}" \
    -P "${PARTITION}" \
    --break 0 \
    --windows-json "${WINDOWS_JSON}" \
    ${CSCINT_OPT} \
    ${SUBSYS_OPT} \
    --include-unified \
    -o "${TEMP_OUT}"

# 5. Verify output file
if [ ! -f "${TEMP_OUT}" ]; then
    echo "[ERROR] Output file was not generated: ${TEMP_OUT}" >&2
    exit 1
fi

PROD_SIZE=$(stat -c%s "${TEMP_OUT}" 2>/dev/null || echo 0)
if [ "${PROD_SIZE}" -lt 400 ]; then
    echo "[ERROR] Generated output file ${TEMP_OUT} is suspiciously small (${PROD_SIZE} bytes)!" >&2
    exit 1
fi

# 6. Atomic copy to EOS
mkdir -p "${TARGET_DIR}"
cp -f "${TEMP_OUT}" "${TARGET_FILE}.tmp"
mv -f "${TARGET_FILE}.tmp" "${TARGET_FILE}"

echo "======================================================================"
echo "[SUCCESS] Partition ${PARTITION} of Run ${RUN} completed."
echo " Output saved to: ${TARGET_FILE} (${PROD_SIZE} bytes)"
echo " Time:            $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
