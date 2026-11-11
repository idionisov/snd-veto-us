#!/bin/bash
# ==============================================================================
# Monitor Reference Time Extraction HTCondor Jobs & EOS Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_PARTS="/eos/user/i/idioniso/Timing/ref_times_parts"

echo "======================================================================"
echo " HTCondor Queue Status"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "reft_|ID" | head -n 25 || condor_q
echo ""

TOTAL_ALL=$(wc -l < "${DIR}/args_partitions_all.txt" 2>/dev/null || echo 0)
TOTAL_CATI=$(wc -l < "${DIR}/args_partitions_catI.txt" 2>/dev/null || echo 0)
TOTAL_CATII=$(wc -l < "${DIR}/args_partitions_catII.txt" 2>/dev/null || echo 0)
TOTAL_CATIII=$(wc -l < "${DIR}/args_partitions_catIII.txt" 2>/dev/null || echo 0)
TOTAL_2023=$(wc -l < "${DIR}/args_partitions_catIII_2023.txt" 2>/dev/null || echo 0)
TOTAL_2024=$(wc -l < "${DIR}/args_partitions_catIII_2024.txt" 2>/dev/null || echo 0)
TOTAL_2025=$(wc -l < "${DIR}/args_partitions_catIII_2025.txt" 2>/dev/null || echo 0)
TOTAL_2026=$(wc -l < "${DIR}/args_partitions_catIII_2026.txt" 2>/dev/null || echo 0)

DONE_CATI=0
DONE_CATII=0
DONE_2023=0
DONE_2024=0
DONE_2025=0
DONE_2026=0

if [ -d "${OUT_PARTS}/catI" ]; then
    DONE_CATI=$(find "${OUT_PARTS}/catI" -name "part_*.root" 2>/dev/null | wc -l)
fi
if [ -d "${OUT_PARTS}/catII" ]; then
    DONE_CATII=$(find "${OUT_PARTS}/catII" -name "part_*.root" 2>/dev/null | wc -l)
fi

# Count completed partitions per year for Cat III
count_year_parts() {
    local args_file="$1"
    local count=0
    if [ ! -f "${args_file}" ] || [ ! -d "${OUT_PARTS}/catIII" ]; then
        echo 0
        return
    fi
    # extract unique runs
    local runs=($(awk '{print $1}' "${args_file}" | sort -u))
    for r in "${runs[@]}"; do
        local rdir="${OUT_PARTS}/catIII/run${r}"
        if [ -d "${rdir}" ]; then
            local n=$(find "${rdir}" -name "part_*.root" 2>/dev/null | wc -l)
            count=$((count + n))
        fi
    done
    echo "${count}"
}

DONE_2023=$(count_year_parts "${DIR}/args_partitions_catIII_2023.txt")
DONE_2024=$(count_year_parts "${DIR}/args_partitions_catIII_2024.txt")
DONE_2025=$(count_year_parts "${DIR}/args_partitions_catIII_2025.txt")
DONE_2026=$(count_year_parts "${DIR}/args_partitions_catIII_2026.txt")
DONE_CATIII=$((DONE_2023 + DONE_2024 + DONE_2025 + DONE_2026))

DONE_ALL=$((DONE_CATI + DONE_CATII + DONE_CATIII))

echo "======================================================================"
echo " Output Partition Progress on EOS (${OUT_PARTS}):"
echo " Category I   (2022)      : ${DONE_CATI} / ${TOTAL_CATI} completed"
echo " Category II  (2022)      : ${DONE_CATII} / ${TOTAL_CATII} completed"
echo " Category III (2023-2026) : ${DONE_CATIII} / ${TOTAL_CATIII} completed"
echo "   - 2023 (10 runs)       : ${DONE_2023} / ${TOTAL_2023} completed"
echo "   - 2024 (10 runs)       : ${DONE_2024} / ${TOTAL_2024} completed"
echo "   - 2025 (10 runs)       : ${DONE_2025} / ${TOTAL_2025} completed"
echo "   - 2026 (10 runs)       : ${DONE_2026} / ${TOTAL_2026} completed"
echo "----------------------------------------------------------------------"
echo " Total                    : ${DONE_ALL} / ${TOTAL_ALL} completed"
echo "======================================================================"
