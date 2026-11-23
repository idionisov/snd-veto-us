#!/bin/bash
set -eo pipefail

# ==============================================================================
# HTCondor Worker: Merge Time-Walk Partitions for a Single Run
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

IN_DIR="/eos/user/i/idioniso/Timing/timewalk_parts/${CAT}/run${RUN}"
OUT_DIR="/eos/user/i/idioniso/Timing/timewalk/runs"
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

if [ ${#PART_FILES[@]} -eq 0 ]; then
    echo "[WARNING] No partition files found in ${IN_DIR}" >&2
    exit 0
fi

echo "======================================================================"
echo " SND@LHC HTCondor Time-Walk Run Merger"
echo " Host:           $(hostname)"
echo " Run:            ${RUN} (${CAT})"
echo " Partitions:     ${#PART_FILES[@]} files"
echo " Destination:    ${OUT_FILE}"
echo " Force Overwrite:${FORCE}"
echo " Start Time:     $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

SCRATCH_BASE="${_CONDOR_SCRATCH_DIR:-/tmp}"
SCRATCH_DIR="${SCRATCH_BASE}/merge_tw_run${RUN}_$$"
mkdir -p "${SCRATCH_DIR}"
trap 'rm -rf "${SCRATCH_DIR}"' EXIT

TMP_OUT="${SCRATCH_DIR}/run${RUN}.root"

# Run hadd with 4 CPU threads in local node scratch
hadd -f -k -j 4 "${TMP_OUT}" "${PART_FILES[@]}"

if [ ! -f "${TMP_OUT}" ]; then
    echo "[ERROR] hadd failed to produce ${TMP_OUT}" >&2
    exit 1
fi

TMP_SZ=$(stat -c%s "${TMP_OUT}" 2>/dev/null || echo 0)
if [ "${TMP_SZ}" -lt 1000 ]; then
    echo "[ERROR] Produced ROOT file is suspiciously small (${TMP_SZ} bytes)!" >&2
    exit 1
fi

# Copy atomically to final EOS path
echo " ~ Copying merged file to ${OUT_FILE}..."
cp -f "${TMP_OUT}" "${OUT_FILE}.tmp"
mv -f "${OUT_FILE}.tmp" "${OUT_FILE}"

FINAL_SIZE=$(stat -c%s "${OUT_FILE}" 2>/dev/null || echo 0)
echo "======================================================================"
echo "[SUCCESS] Finished merging Run ${RUN} (${#PART_FILES[@]} partitions)"
echo " Output:    ${OUT_FILE} (${FINAL_SIZE} bytes)"
echo " End Time:  $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"
