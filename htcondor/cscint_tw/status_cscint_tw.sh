#!/bin/bash
# ==============================================================================
# Monitor Time-Walk Corrected c_scint Extraction HTCondor Jobs & EOS Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_PARTS="/eos/user/i/idioniso/Timing/cscint_tw_parts"

echo "======================================================================"
echo " HTCondor Queue Status (cscint_tw)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "cscint_tw_run|run_cscint_tw|ID" | head -n 30 || condor_q
echo ""

echo "======================================================================"
echo " Time-Walk Corrected c_scint Partition Extraction Progress"
echo " Destination: ${OUT_PARTS}"
echo "======================================================================"

check_progress() {
    local label="$1"
    local args_file="$2"
    local total=0
    local done=0

    if [ ! -f "${args_file}" ]; then
        return
    fi

    while read -r r p cat; do
        [ -z "$r" ] && continue
        total=$((total + 1))
        local target="${OUT_PARTS}/${cat}/run${r}/part_${p}.root"
        if [ -f "$target" ]; then
            local sz=$(stat -c%s "$target" 2>/dev/null || echo 0)
            if [ "$sz" -gt 1000 ]; then
                done=$((done + 1))
            fi
        fi
    done < "${args_file}"

    local pct="0.0%"
    if [ "$total" -gt 0 ]; then
        pct=$(awk "BEGIN {printf \"%.1f%%\", ($done/$total)*100}")
    fi

    printf "%-18s | %-12d | %-12d | %-10s\n" "${label}" "${total}" "${done}" "${pct}"
}

printf "%-18s | %-12s | %-12s | %-10s\n" "Group / Year" "Total Parts" "Extracted" "Progress"
echo "----------------------------------------------------------------------"

check_progress "Cat II (2022)" "${DIR}/args_partitions_catII_max50.txt"
check_progress "Cat III (2023)" "${DIR}/args_partitions_catIII_2023_max50.txt"
check_progress "Cat III (2024)" "${DIR}/args_partitions_catIII_2024_max50.txt"
check_progress "Cat III (2025)" "${DIR}/args_partitions_catIII_2025_max50.txt"
check_progress "Cat III (2026)" "${DIR}/args_partitions_catIII_2026_max50.txt"
echo "----------------------------------------------------------------------"
check_progress "Total (All Active)" "${DIR}/args_partitions_all_max50.txt"
echo "======================================================================"
