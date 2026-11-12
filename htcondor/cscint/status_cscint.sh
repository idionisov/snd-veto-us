#!/bin/bash
# ==============================================================================
# Monitor cscint (SiPM Ref Diff) Extraction HTCondor Jobs & EOS Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_PARTS="/eos/user/i/idioniso/Timing/cscint_parts"

echo "======================================================================"
echo " HTCondor Queue Status (cscint)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "cscint_run|ID" | head -n 20 || condor_q
echo ""

TOTAL_ALL=$(wc -l < "${DIR}/args_partitions_all.txt" 2>/dev/null || echo 0)
TOTAL_CATI=$(wc -l < "${DIR}/args_partitions_catI.txt" 2>/dev/null || echo 0)
TOTAL_CATII=$(wc -l < "${DIR}/args_partitions_catII.txt" 2>/dev/null || echo 0)

DONE_CATI=0
DONE_CATII=0
if [ -d "${OUT_PARTS}/catI" ]; then
    DONE_CATI=$(find "${OUT_PARTS}/catI" -name "part_*.root" 2>/dev/null | wc -l)
fi
if [ -d "${OUT_PARTS}/catII" ]; then
    DONE_CATII=$(find "${OUT_PARTS}/catII" -name "part_*.root" 2>/dev/null | wc -l)
fi
DONE_ALL=$((DONE_CATI + DONE_CATII))

echo "======================================================================"
echo " Output Partition Progress on EOS (${OUT_PARTS}):"
if [ -n "$1" ]; then
    RUN="$1"
    RUN_PARTS=$(find "${OUT_PARTS}" -path "*/run${RUN}/part_*.root" 2>/dev/null | wc -l)
    TOTAL_RUN=0
    if [ -f "${DIR}/args_run${RUN}.txt" ]; then
        TOTAL_RUN=$(wc -l < "${DIR}/args_run${RUN}.txt")
    elif grep -q "^${RUN} " "${DIR}/args_partitions_all.txt" 2>/dev/null; then
        TOTAL_RUN=$(grep -c "^${RUN} " "${DIR}/args_partitions_all.txt")
    fi
    echo " Run ${RUN} Progress : ${RUN_PARTS} / ${TOTAL_RUN} partitions completed"
fi
echo " Category I  : ${DONE_CATI} / ${TOTAL_CATI} completed"
echo " Category II : ${DONE_CATII} / ${TOTAL_CATII} completed"
echo " Total       : ${DONE_ALL} / ${TOTAL_ALL} completed"
echo "======================================================================"
