#!/bin/bash
set -eo pipefail

source /afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh

RUNS_DIR="/eos/user/i/idioniso/Timing/cscint/runs"
CATS_DIR="/eos/user/i/idioniso/Timing/cscint/categories"
mkdir -p "${CATS_DIR}"

CAT2_RUNS=(5119 5120 5122 5125 5128 5130 5132 5133 5136 5144 5150 5152 5154 5157 5159 5170 5171 5236 5239 5241 5247 5253 5257 5259 5262 5263 5350 5373 5377 5389 5396 5399 5408)
CAT3_2023_RUNS=(6079 6568 6574 6577 6590 6593 6596 6640 6663 6667)

# 1. Merge Cat II
echo "======================================================================"
echo " Merging Cat II (${#CAT2_RUNS[@]} runs) -> ${CATS_DIR}/catII.root"
echo "======================================================================"
CAT2_FILES=()
for r in "${CAT2_RUNS[@]}"; do
    rf="${RUNS_DIR}/run${r}.root"
    if [ -f "${rf}" ]; then
        CAT2_FILES+=("${rf}")
    else
        echo " [WARNING] Missing ${rf}"
    fi
done

if [ ${#CAT2_FILES[@]} -gt 0 ]; then
    TMP_CAT2="${TMPDIR:-/tmp}/catII_$$.root"
    hadd -f -k -j 4 "${TMP_CAT2}" "${CAT2_FILES[@]}"
    cp -f "${TMP_CAT2}" "${CATS_DIR}/catII.root"
    rm -f "${TMP_CAT2}"
    echo "[SUCCESS] Generated ${CATS_DIR}/catII.root ($(stat -c%s "${CATS_DIR}/catII.root" 2>/dev/null) bytes)"
fi

# 2. Merge Cat III (2023)
echo "======================================================================"
echo " Merging Cat III 2023 (${#CAT3_2023_RUNS[@]} runs) -> ${CATS_DIR}/catIII_2023.root"
echo "======================================================================"
CAT3_FILES=()
for r in "${CAT3_2023_RUNS[@]}"; do
    rf="${RUNS_DIR}/run${r}.root"
    if [ -f "${rf}" ]; then
        CAT3_FILES+=("${rf}")
    else
        echo " [WARNING] Missing ${rf}"
    fi
done

if [ ${#CAT3_FILES[@]} -gt 0 ]; then
    TMP_CAT3="${TMPDIR:-/tmp}/catIII_2023_$$.root"
    hadd -f -k -j 4 "${TMP_CAT3}" "${CAT3_FILES[@]}"
    cp -f "${TMP_CAT3}" "${CATS_DIR}/catIII_2023.root"
    rm -f "${TMP_CAT3}"
    echo "[SUCCESS] Generated ${CATS_DIR}/catIII_2023.root ($(stat -c%s "${CATS_DIR}/catIII_2023.root" 2>/dev/null) bytes)"
fi

echo "======================================================================"
echo " [FINISHED] Merging complete."
echo "======================================================================"
