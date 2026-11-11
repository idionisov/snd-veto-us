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

SUFFIX=""
if [ "$1" == "--max15" ] || [ "$1" == "max15" ] || [ "$1" == "15" ]; then
    SUFFIX="_max15"
elif [[ "$1" =~ ^_ ]]; then
    SUFFIX="$1"
fi

get_lines() {
    [ -f "$1" ] && wc -l < "$1" || echo 0
}

TOTAL_ALL=$(get_lines "${DIR}/args_partitions_all${SUFFIX}.txt")
TOTAL_CATI=$(get_lines "${DIR}/args_partitions_catI${SUFFIX}.txt")
TOTAL_CATII=$(get_lines "${DIR}/args_partitions_catII${SUFFIX}.txt")
TOTAL_CATIII=$(get_lines "${DIR}/args_partitions_catIII${SUFFIX}.txt")
TOTAL_2023=$(get_lines "${DIR}/args_partitions_catIII_2023${SUFFIX}.txt")
TOTAL_2024=$(get_lines "${DIR}/args_partitions_catIII_2024${SUFFIX}.txt")
TOTAL_2025=$(get_lines "${DIR}/args_partitions_catIII_2025${SUFFIX}.txt")
TOTAL_2026=$(get_lines "${DIR}/args_partitions_catIII_2026${SUFFIX}.txt")

if [ "${TOTAL_ALL}" -eq 0 ] && [ "${TOTAL_CATIII}" -gt 0 ]; then
    TOTAL_ALL=$((TOTAL_CATI + TOTAL_CATII + TOTAL_CATIII))
fi

DONE_CATI=0
DONE_CATII=0
DONE_2023=0
DONE_2024=0
DONE_2025=0
DONE_2026=0

# Count completed partitions specifically listed in args_file
count_args_parts() {
    local args_file="$1"
    local count=0
    if [ ! -f "${args_file}" ]; then
        echo 0
        return
    fi
    while read -r r p cat; do
        if [ -f "${OUT_PARTS}/${cat}/run${r}/part_${p}.root" ]; then
            count=$((count + 1))
        fi
    done < "${args_file}"
    echo "${count}"
}

if [ -n "${SUFFIX}" ]; then
    DONE_CATI=$(count_args_parts "${DIR}/args_partitions_catI${SUFFIX}.txt")
    DONE_CATII=$(count_args_parts "${DIR}/args_partitions_catII${SUFFIX}.txt")
    DONE_2023=$(count_args_parts "${DIR}/args_partitions_catIII_2023${SUFFIX}.txt")
    DONE_2024=$(count_args_parts "${DIR}/args_partitions_catIII_2024${SUFFIX}.txt")
    DONE_2025=$(count_args_parts "${DIR}/args_partitions_catIII_2025${SUFFIX}.txt")
    DONE_2026=$(count_args_parts "${DIR}/args_partitions_catIII_2026${SUFFIX}.txt")
else
    if [ -d "${OUT_PARTS}/catI" ]; then
        DONE_CATI=$(find "${OUT_PARTS}/catI" -name "part_*.root" 2>/dev/null | wc -l)
    fi
    if [ -d "${OUT_PARTS}/catII" ]; then
        DONE_CATII=$(find "${OUT_PARTS}/catII" -name "part_*.root" 2>/dev/null | wc -l)
    fi
    count_year_parts() {
        local args_file="$1"
        local count=0
        if [ ! -f "${args_file}" ] || [ ! -d "${OUT_PARTS}/catIII" ]; then
            echo 0
            return
        fi
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
fi
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
