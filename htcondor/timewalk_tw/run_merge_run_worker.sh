#!/bin/bash
set -eo pipefail

# ==============================================================================
# HTCondor Worker: Merge Time-Walk Partitions for a Single Run (Iteration 2)
#
# Arguments:
#   $1: RUN         (e.g., 5119)
#   $2: CATEGORY    (e.g., catII or catIII)
# ==============================================================================

RUN="$1"
CAT="$2"
FORCE="${FORCE:-1}"

if [ -z "${RUN}" ] || [ -z "${CAT}" ]; then
    echo "Usage: $0 <run> <category>" >&2
    exit 1
fi

WORK_DIR="/afs/cern.ch/work/i/idioniso/snd-veto-us"
if [ -f "${WORK_DIR}/sndswEnv.sh" ]; then
    source "${WORK_DIR}/sndswEnv.sh"
else
    echo "[ERROR] sndswEnv.sh not found at ${WORK_DIR}!" >&2
    exit 1
fi

IN_DIR="/eos/user/i/idioniso/Timing/timewalk_tw_parts/${CAT}/run${RUN}"
OUT_DIR="/eos/user/i/idioniso/Timing/timewalk_tw/runs"
OUT_FILE="${OUT_DIR}/run${RUN}.root"

mkdir -p "${OUT_DIR}"

# Check existing file if force is not requested
if [ "${FORCE}" != "1" ] && [ -f "${OUT_FILE}" ]; then
    FSIZE=$(stat -c%s "${OUT_FILE}" 2>/dev/null || echo 0)
    if [ "${FSIZE}" -gt 1000000 ]; then
        echo "[INFO] Run ${RUN} (${CAT}) already merged: ${OUT_FILE} (${FSIZE} bytes). Skipping."
        exit 0
    fi
fi

# Find all partition files
mapfile -t PART_FILES < <(find "${IN_DIR}" -name "part_*.root" 2>/dev/null | sort)
N_PARTS=${#PART_FILES[@]}

if [ "${N_PARTS}" -eq 0 ]; then
    echo "[ERROR] No partition files found in ${IN_DIR}!" >&2
    exit 1
fi

echo "======================================================================"
echo " Merging Run ${RUN} (${CAT}): ${N_PARTS} partitions"
echo " Host:        $(hostname)"
echo " Start Time:  $(date '+%Y-%m-%d %H:%M:%S')"
echo " Destination: ${OUT_FILE}"
echo "======================================================================"

SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/merge_tw_${RUN}_$$"
mkdir -p "${SCRATCH_DIR}"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

TEMP_OUT="${SCRATCH_DIR}/run${RUN}.root"

hadd -f -k -j 4 "${TEMP_OUT}" "${PART_FILES[@]}"

if [ ! -f "${TEMP_OUT}" ]; then
    echo "[ERROR] hadd output was not generated!" >&2
    exit 1
fi

MERGED_SIZE=$(stat -c%s "${TEMP_OUT}" 2>/dev/null || echo 0)
if [ "${MERGED_SIZE}" -lt 100000 ]; then
    echo "[ERROR] Merged file is suspiciously small: ${MERGED_SIZE} bytes!" >&2
    exit 1
fi

echo " ~ Transferring merged ROOT file to EOS..."
cp -f "${TEMP_OUT}" "${OUT_FILE}.tmp"
mv -f "${OUT_FILE}.tmp" "${OUT_FILE}"

echo "======================================================================"
echo "[SUCCESS] Run ${RUN} merged successfully: ${OUT_FILE} (${MERGED_SIZE} bytes)"
echo " End Time: $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
