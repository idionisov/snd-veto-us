#!/bin/bash
set -eo pipefail

# Environment setup
source /afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh

OUT_DIR="/eos/user/i/idioniso/Timing/cscint/categories"
CAT2_ROOT="${OUT_DIR}/catII.root"
CAT3_2023_ROOT="${OUT_DIR}/catIII_2023.root"
MERGED_OUTPUT="${OUT_DIR}/catII_catIII_2023.root"

echo "======================================================================"
echo " Starting HTCondor Merge: Cat II + Cat III (2023 only)"
echo " Output Target: ${MERGED_OUTPUT}"
echo "======================================================================"

# Step 1: Merge 2023 Cat III partitions (runs 6079 to 6667, matching run6*)
echo " ~ [1/2] Merging 2023 Cat III runs (run6*) -> ${CAT3_2023_ROOT}..."
hadd -f -j 4 "${CAT3_2023_ROOT}" /eos/user/i/idioniso/Timing/cscint_parts/catIII/run6*/part_*.root

# Step 2: Combine catII.root and catIII_2023.root into final output
echo " ~ [2/2] Combining Cat II and 2023 Cat III -> ${MERGED_OUTPUT}..."
hadd -f "${MERGED_OUTPUT}" "${CAT2_ROOT}" "${CAT3_2023_ROOT}"

echo "======================================================================"
echo " [SUCCESS] Merged output written to: ${MERGED_OUTPUT}"
ls -lh "${MERGED_OUTPUT}"
echo "======================================================================"
