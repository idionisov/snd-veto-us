#!/bin/bash
# ==============================================================================
# Monitor Status of cscint_tw Fit Jobs & Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FITS_DIR="/eos/user/i/idioniso/Timing/cscint_tw/fits"
FITS_ROOT_DIR="/eos/user/i/idioniso/Timing/cscint_tw/fits_root"

echo "======================================================================"
echo " HTCondor Queue Status (cscint_tw_fit)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "run_fit_worker|fit_|ID" | head -n 40 || condor_q

echo ""
echo "======================================================================"
echo " Time-Walk Corrected c_scint Fit Status"
echo " Destination JSON: ${FITS_DIR}"
echo " Destination ROOT: ${FITS_ROOT_DIR}"
echo "======================================================================"

check_group() {
    local label="$1"
    local args_file="$2"
    local total=0
    local fitted_json=0
    local fitted_root=0
    local complete=0
    local missing=()

    if [ ! -f "${args_file}" ]; then
        return
    fi

    while read -r r; do
        [ -z "$r" ] && continue
        total=$((total + 1))
        
        local jf="${FITS_DIR}/run${r}_cscint.json"
        local rf="${FITS_ROOT_DIR}/run${r}.root"
        local has_j=0
        local has_r=0

        if [ -f "$jf" ] && [ "$(stat -c%s "$jf" 2>/dev/null || echo 0)" -gt 10000 ]; then
            fitted_json=$((fitted_json + 1))
            has_j=1
        fi

        if [ -f "$rf" ] && [ "$(stat -c%s "$rf" 2>/dev/null || echo 0)" -gt 1000000 ]; then
            fitted_root=$((fitted_root + 1))
            has_r=1
        fi

        if [ "$has_j" -eq 1 ] && [ "$has_r" -eq 1 ]; then
            complete=$((complete + 1))
        else
            missing+=("$r")
        fi
    done < "${args_file}"

    local pct="0.0%"
    if [ "$total" -gt 0 ]; then
        pct=$(awk "BEGIN {printf \"%.1f%%\", ($complete/$total)*100}")
    fi

    printf "%-18s | %-8d | %-8d | %-8d | %-8d | %-8s\n" \
        "${label}" "${total}" "${fitted_json}" "${fitted_root}" "${complete}" "${pct}"

    if [ ${#missing[@]} -gt 0 ] && [ ${#missing[@]} -le 10 ]; then
        echo "   -> Incomplete: ${missing[*]}"
    fi
}

printf "%-18s | %-8s | %-8s | %-8s | %-8s | %-8s\n" \
    "Category / Year" "Total" "JSONs" "ROOTs" "Both OK" "Progress"
echo "--------------------------------------------------------------------------------"

check_group "Cat II (2022)" "${DIR}/args_fit_catII.txt"
check_group "Cat III (2023)" "${DIR}/args_fit_catIII_2023.txt"
check_group "Cat III (2025)" "${DIR}/args_fit_catIII_2025.txt"
echo "--------------------------------------------------------------------------------"
check_group "Total (All Runs)" "${DIR}/args_fit_all.txt"
echo "======================================================================"
