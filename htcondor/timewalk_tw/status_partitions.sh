#!/bin/bash
# ==============================================================================
# Monitor Status of Time-Walk Iteration 2 Partition Jobs & EOS Outputs
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARTS_BASE="/eos/user/i/idioniso/Timing/timewalk_tw_parts"

echo "======================================================================"
echo " HTCondor Queue Status (timewalk_tw)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "run_timewalk_worker|tw_run|ID" | head -n 40 || condor_q

echo ""
echo "======================================================================"
echo " Time-Walk Iteration 2 Partition Files Status"
echo " Destination: ${PARTS_BASE}"
echo "======================================================================"

check_partition_group() {
    local label="$1"
    local args_file="$2"
    local total=0
    local found=0
    local total_bytes=0

    if [ ! -f "${args_file}" ]; then
        return
    fi

    while read -r r p cat; do
        [ -z "$r" ] && continue
        total=$((total + 1))
        local target="${PARTS_BASE}/${cat}/run${r}/part_${p}.root"
        if [ -f "$target" ]; then
            local sz=$(stat -c%s "$target" 2>/dev/null || echo 0)
            if [ "$sz" -gt 1000 ]; then
                found=$((found + 1))
                total_bytes=$((total_bytes + sz))
            fi
        fi
    done < "${args_file}"

    local pct="0.0%"
    if [ "$total" -gt 0 ]; then
        pct=$(awk "BEGIN {printf \"%.1f%%\", ($found/$total)*100}")
    fi
    local mb=0
    if [ "$found" -gt 0 ]; then
        mb=$(awk "BEGIN {printf \"%.1f MB\", $total_bytes/1000000}")
    fi

    printf "%-18s | %-10d | %-10d | %-10s | %-12s\n" \
        "${label}" "${total}" "${found}" "${pct}" "${mb}"
}

printf "%-18s | %-10s | %-10s | %-10s | %-12s\n" \
    "Category / Year" "Total Parts" "Extracted" "Progress" "Total Size"
echo "----------------------------------------------------------------------"

check_partition_group "Cat II (2022)" "${DIR}/args_partitions_catII_max50.txt"
check_partition_group "Cat III (2023)" "${DIR}/args_partitions_catIII_2023_max50.txt"
check_partition_group "Cat III (2025)" "${DIR}/args_partitions_catIII_2025_max50.txt"
echo "----------------------------------------------------------------------"
check_partition_group "Total (All 53 Runs)" "${DIR}/args_partitions_all_max50.txt"
echo "======================================================================"
