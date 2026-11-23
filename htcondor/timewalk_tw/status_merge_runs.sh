#!/bin/bash
# ==============================================================================
# Monitor Status of Time-Walk Iteration 2 Run Merging Jobs & Merged ROOT Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNS_DIR="/eos/user/i/idioniso/Timing/timewalk_tw/runs"

echo "======================================================================"
echo " HTCondor Queue Status (merge_runs)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "run_merge_run_worker|merge_run|ID" | head -n 40 || condor_q

echo ""
echo "======================================================================"
echo " Time-Walk Iteration 2 Merged Runs Status"
echo " Destination: ${RUNS_DIR}"
echo "======================================================================"

check_merge_group() {
    local label="$1"
    local args_file="$2"
    local total=0
    local merged=0
    local missing=()
    local total_bytes=0

    if [ ! -f "${args_file}" ]; then
        return
    fi

    while read -r r cat; do
        [ -z "$r" ] && continue
        total=$((total + 1))
        
        local rf="${RUNS_DIR}/run${r}.root"
        if [ -f "$rf" ]; then
            local sz=$(stat -c%s "$rf" 2>/dev/null || echo 0)
            if [ "$sz" -gt 1000000 ]; then
                merged=$((merged + 1))
                total_bytes=$((total_bytes + sz))
            else
                missing+=("$r")
            fi
        else
            missing+=("$r")
        fi
    done < "${args_file}"

    local pct="0.0%"
    if [ "$total" -gt 0 ]; then
        pct=$(awk "BEGIN {printf \"%.1f%%\", ($merged/$total)*100}")
    fi
    local avg_mb=0
    if [ "$merged" -gt 0 ]; then
        avg_mb=$(awk "BEGIN {printf \"%.1f MB\", ($total_bytes/$merged)/1000000}")
    fi

    printf "%-18s | %-10d | %-10d | %-10s | %-12s\n" \
        "${label}" "${total}" "${merged}" "${pct}" "${avg_mb}"

    if [ ${#missing[@]} -gt 0 ] && [ ${#missing[@]} -le 10 ]; then
        echo "   -> Not merged: ${missing[*]}"
    fi
}

printf "%-18s | %-10s | %-10s | %-10s | %-12s\n" \
    "Category / Year" "Total Runs" "Merged" "Progress" "Avg Run Size"
echo "----------------------------------------------------------------------"

check_merge_group "Cat II (2022)" "${DIR}/args_merge_runs_catII.txt"
check_merge_group "Cat III (2023)" "${DIR}/args_merge_runs_catIII_2023.txt"
check_merge_group "Cat III (2025)" "${DIR}/args_merge_runs_catIII_2025.txt"
echo "----------------------------------------------------------------------"
check_merge_group "Total (All 53 Runs)" "${DIR}/args_merge_runs_all.txt"
echo "======================================================================"
