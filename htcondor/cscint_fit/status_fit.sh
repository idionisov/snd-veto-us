#!/bin/bash
# ==============================================================================
# Monitor Status of cscint_fit Jobs & Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo " HTCondor Queue Status (cscint_fit)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "fit_run|ID" | head -n 45 || condor_q

echo ""
echo "======================================================================"
echo " cscint Fit Outputs Status (JSON & ROOT files)"
echo " Destination JSON: /eos/user/i/idioniso/Timing/cscint/fits"
echo " Destination ROOT: /eos/user/i/idioniso/Timing/cscint/fits_root"
echo "======================================================================"

check_group() {
    local label="$1"
    local args_file="$2"
    local total=0
    local json_ok=0
    local root_ok=0
    local both_ok=0
    local missing=()

    [ ! -f "${args_file}" ] && return

    while read -r r; do
        [ -z "$r" ] && continue
        total=$((total + 1))
        
        local jf="/eos/user/i/idioniso/Timing/cscint/fits/run${r}_cscint.json"
        local rf="/eos/user/i/idioniso/Timing/cscint/fits_root/run${r}.root"

        local has_j=0
        local has_r=0

        if [ -f "$jf" ] && [ $(stat -c%s "$jf" 2>/dev/null || echo 0) -gt 1000 ]; then
            has_j=1
            json_ok=$((json_ok + 1))
        fi

        if [ -f "$rf" ] && [ $(stat -c%s "$rf" 2>/dev/null || echo 0) -gt 1000000 ]; then
            has_r=1
            root_ok=$((root_ok + 1))
        fi

        if [ "$has_j" -eq 1 ] && [ "$has_r" -eq 1 ]; then
            both_ok=$((both_ok + 1))
        else
            missing+=("$r")
        fi
    done < "${args_file}"

    local pct="0.0%"
    if [ "$total" -gt 0 ]; then
        pct=$(awk "BEGIN {printf \"%.1f%%\", ($both_ok/$total)*100}")
    fi

    printf "%-18s | %-10d | %-11d | %-11d | %-10s | %-10s\n" \
        "${label}" "${total}" "${json_ok}" "${root_ok}" "${both_ok}" "${pct}"

    if [ ${#missing[@]} -gt 0 ]; then
        echo "   -> Incomplete (${#missing[@]} runs): ${missing[*]}"
    fi
}

printf "%-18s | %-10s | %-11s | %-11s | %-10s | %-10s\n" \
    "Category / Year" "Total Runs" "JSONs Ready" "ROOTs Ready" "Both Ready" "Progress"
echo "----------------------------------------------------------------------------------"

check_group "Cat II (2022)" "${DIR}/args_catII.txt"
check_group "Cat III (2023)" "${DIR}/args_catIII_2023.txt"
check_group "Cat III (2024)" "${DIR}/args_catIII_2024.txt"
check_group "Cat III (2025)" "${DIR}/args_catIII_2025.txt"
check_group "Cat III (2026)" "${DIR}/args_catIII_2026.txt"
echo "=================================================================================="
