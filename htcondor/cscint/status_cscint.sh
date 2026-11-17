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

# Resolve argument files (prefer max40 if generated, fallback to max20, then unconstrained)
P_SUFFIX="max40"
if [ ! -f "${DIR}/args_partitions_all_max40.txt" ]; then
    P_SUFFIX="max20"
fi

ARGS_ALL="${DIR}/args_partitions_all_${P_SUFFIX}.txt"
[ ! -f "${ARGS_ALL}" ] && ARGS_ALL="${DIR}/args_partitions_all.txt"

ARGS_CATI="${DIR}/args_partitions_catI_${P_SUFFIX}.txt"
[ ! -f "${ARGS_CATI}" ] && ARGS_CATI="${DIR}/args_partitions_catI.txt"

ARGS_CATII="${DIR}/args_partitions_catII_${P_SUFFIX}.txt"
[ ! -f "${ARGS_CATII}" ] && ARGS_CATII="${DIR}/args_partitions_catII.txt"

ARGS_CATIII="${DIR}/args_partitions_catIII_${P_SUFFIX}.txt"

TOTAL_ALL=$(wc -l < "${ARGS_ALL}" 2>/dev/null || echo 0)
TOTAL_CATI=$(wc -l < "${ARGS_CATI}" 2>/dev/null || echo 0)
TOTAL_CATII=$(wc -l < "${ARGS_CATII}" 2>/dev/null || echo 0)
TOTAL_CATIII=$(wc -l < "${ARGS_CATIII}" 2>/dev/null || echo 0)

DONE_CATI=0
DONE_CATII=0
DONE_CATIII=0
if [ -d "${OUT_PARTS}/catI" ]; then
    DONE_CATI=$(find "${OUT_PARTS}/catI" -maxdepth 2 -name "part_*.root" 2>/dev/null | wc -l)
fi
if [ -d "${OUT_PARTS}/catII" ]; then
    DONE_CATII=$(find "${OUT_PARTS}/catII" -maxdepth 2 -name "part_*.root" 2>/dev/null | wc -l)
fi
if [ -d "${OUT_PARTS}/catIII" ]; then
    DONE_CATIII=$(find "${OUT_PARTS}/catIII" -maxdepth 2 -name "part_*.root" 2>/dev/null | wc -l)
fi
DONE_ALL=$((DONE_CATI + DONE_CATII + DONE_CATIII))

echo "======================================================================"
echo " Output Partition Progress on EOS (${OUT_PARTS}):"
if [ -n "$1" ]; then
    RUN="$1"
    RUN_PARTS=$(find "${OUT_PARTS}" -path "*/run${RUN}/part_*.root" 2>/dev/null | wc -l)
    TOTAL_RUN=0
    if [ -f "${DIR}/args_run${RUN}.txt" ]; then
        TOTAL_RUN=$(wc -l < "${DIR}/args_run${RUN}.txt")
    elif grep -q "^${RUN} " "${ARGS_ALL}" 2>/dev/null; then
        TOTAL_RUN=$(grep -c "^${RUN} " "${ARGS_ALL}")
    fi
    echo " Run ${RUN} Progress : ${RUN_PARTS} / ${TOTAL_RUN} partitions completed"
fi
echo " Category I   : ${DONE_CATI} / ${TOTAL_CATI} completed"
echo " Category II  : ${DONE_CATII} / ${TOTAL_CATII} completed"
echo " Category III : ${DONE_CATIII} / ${TOTAL_CATIII} completed"
echo " Total        : ${DONE_ALL} / ${TOTAL_ALL} completed"
echo "======================================================================"
