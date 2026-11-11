#!/bin/bash
# ==============================================================================
# Monitor Reference Time Extraction HTCondor Jobs & EOS Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_PARTS="/eos/user/i/idioniso/Timing/ref_times_parts"

echo "======================================================================"
echo " HTCondor Queue Status"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "reft_run|ID" | head -n 20 || condor_q
echo ""

TOTAL_ALL=$(wc -l < "${DIR}/args_partitions_all.txt" 2>/dev/null || echo 0)
TOTAL_CATI=$(wc -l < "${DIR}/args_partitions_catI.txt" 2>/dev/null || echo 0)
TOTAL_CATII=$(wc -l < "${DIR}/args_partitions_catII.txt" 2>/dev/null || echo 0)
TOTAL_CATIII=$(wc -l < "${DIR}/args_partitions_catIII.txt" 2>/dev/null || echo 0)

DONE_CATI=0
DONE_CATII=0
DONE_CATIII=0
if [ -d "${OUT_PARTS}/catI" ]; then
    DONE_CATI=$(find "${OUT_PARTS}/catI" -name "part_*.root" 2>/dev/null | wc -l)
fi
if [ -d "${OUT_PARTS}/catII" ]; then
    DONE_CATII=$(find "${OUT_PARTS}/catII" -name "part_*.root" 2>/dev/null | wc -l)
fi
if [ -d "${OUT_PARTS}/catIII" ]; then
    DONE_CATIII=$(find "${OUT_PARTS}/catIII" -name "part_*.root" 2>/dev/null | wc -l)
fi
DONE_ALL=$((DONE_CATI + DONE_CATII + DONE_CATIII))

echo "======================================================================"
echo " Output Partition Progress on EOS (${OUT_PARTS}):"
echo " Category I   (2022)      : ${DONE_CATI} / ${TOTAL_CATI} completed"
echo " Category II  (2022)      : ${DONE_CATII} / ${TOTAL_CATII} completed"
echo " Category III (2023-2026) : ${DONE_CATIII} / ${TOTAL_CATIII} completed"
echo " Total                    : ${DONE_ALL} / ${TOTAL_ALL} completed"
echo "======================================================================"
