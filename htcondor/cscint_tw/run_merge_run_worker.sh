#!/bin/bash
set -eo pipefail

# ==============================================================================
# HTCondor Worker: Merge Time-Walk Corrected c_scint Partitions for a Single Run
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

IN_DIR="/eos/user/i/idioniso/Timing/cscint_tw_parts/${CAT}/run${RUN}"
OUT_DIR="/eos/user/i/idioniso/Timing/cscint_tw/runs"
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

# Find all partition ROOT files
mapfile -t PART_FILES < <(find "${IN_DIR}" -name "part_*.root" -type f 2>/dev/null | sort -V)
NUM_PARTS="${#PART_FILES[@]}"

if [ "${NUM_PARTS}" -eq 0 ]; then
    echo "[ERROR] No partition files found in ${IN_DIR}!" >&2
    exit 1
fi

echo "======================================================================"
echo " SND@LHC HTCondor Worker: Merge cscint_tw Partitions"
echo " Host:        $(hostname)"
echo " Run:         ${RUN} (${CAT})"
echo " Partitions:  ${NUM_PARTS} files"
echo " Source:      ${IN_DIR}"
echo " Destination: ${OUT_FILE}"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/merge_cscint_tw_run${RUN}_$$"
mkdir -p "${SCRATCH_DIR}"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

TEMP_OUT="${SCRATCH_DIR}/run${RUN}.root"

echo " ~ Merging ${NUM_PARTS} partitions into local scratch with hadd -j 4..."
hadd -f -k -j 4 "${TEMP_OUT}" "${PART_FILES[@]}"

if [ ! -f "${TEMP_OUT}" ]; then
    echo "[ERROR] Merged file not produced: ${TEMP_OUT}" >&2
    exit 1
fi

OUT_SIZE=$(stat -c%s "${TEMP_OUT}" 2>/dev/null || echo 0)
if [ "${OUT_SIZE}" -lt 5000 ]; then
    echo "[ERROR] Produced merged file is suspiciously small (${OUT_SIZE} bytes)!" >&2
    exit 1
fi

echo " ~ Transferring merged ROOT file to EOS: ${OUT_FILE}..."
cp -f "${TEMP_OUT}" "${OUT_FILE}.tmp"
mv -f "${OUT_FILE}.tmp" "${OUT_FILE}"

echo "======================================================================"
echo "[SUCCESS] Run ${RUN} merged successfully (${NUM_PARTS} partitions, ${OUT_SIZE} bytes)."
echo " Saved to: ${OUT_FILE}"
echo " Time:     $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
