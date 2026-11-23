#!/bin/bash
set -eo pipefail

RUN="$1"
CAT="$2"
FORCE="${FORCE:-1}"

if [ -z "${RUN}" ] || [ -z "${CAT}" ]; then
    echo "Usage: $0 <run> <cat>"
    exit 1
fi

# Setup sndsw environment
if [ -f "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh" ]; then
    source "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh"
fi

IN_DIR="/eos/user/i/idioniso/Timing/cscint_parts/${CAT}/run${RUN}"
OUT_DIR="/eos/user/i/idioniso/Timing/cscint/runs"
OUT_FILE="${OUT_DIR}/run${RUN}.root"

mkdir -p "${OUT_DIR}"

# Check if already completed and non-empty
if [ "${FORCE}" != "1" ] && [ -f "${OUT_FILE}" ]; then
    FSIZE=$(stat -c%s "${OUT_FILE}" 2>/dev/null || echo 0)
    if [ "${FSIZE}" -gt 1000 ]; then
        echo "[INFO] Run ${RUN} (${CAT}) already merged: ${OUT_FILE} (${FSIZE} bytes). Skipping."
        exit 0
    fi
fi

# Find partition files
mapfile -t PART_FILES < <(find "${IN_DIR}" -name "part_*.root" 2>/dev/null | sort)

if [ ${#PART_FILES[@]} -eq 0 ]; then
    echo "[WARNING] No partition files found in ${IN_DIR}"
    exit 0
fi

echo "======================================================================"
echo " Merging run ${RUN} (${CAT}): ${#PART_FILES[@]} partitions"
echo " Target: ${OUT_FILE}"
echo "======================================================================"

SCRATCH="${_CONDOR_SCRATCH_DIR:-/tmp}/merge_run${RUN}_$$"
mkdir -p "${SCRATCH}"
trap 'rm -rf "${SCRATCH}"' EXIT

TMP_OUT="${SCRATCH}/run${RUN}.root"

# Merge partitions with multi-threading into local scratch
hadd -f -k -j 4 "${TMP_OUT}" "${PART_FILES[@]}"

# Copy atomically to final EOS destination
cp -f "${TMP_OUT}" "${OUT_FILE}.tmp"
mv -f "${OUT_FILE}.tmp" "${OUT_FILE}"

FINAL_SIZE=$(stat -c%s "${OUT_FILE}" 2>/dev/null || echo 0)
echo "[SUCCESS] Finished merging run ${RUN} -> ${OUT_FILE} (${FINAL_SIZE} bytes)"
