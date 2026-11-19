#!/bin/bash
# ==============================================================================
# Monitor Time-Walk Fitting HTCondor Jobs & Calibration JSONs
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IN_DIR="/eos/user/i/idioniso/Timing/timewalk/runs"
OUT_DIR="/eos/user/i/idioniso/Timing/timewalk/fits"

echo "======================================================================"
echo " HTCondor Queue Status (fit_tw)"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "fit_tw_run|ID" | head -n 25 || condor_q
echo ""

get_cat() {
    local r="$1"
    if [ "$r" -le 5116 ] || { [ "$r" -ge 5175 ] && [ "$r" -le 5192 ]; }; then
        echo "catI"
    elif { [ "$r" -ge 5117 ] && [ "$r" -le 5174 ]; } || { [ "$r" -ge 5193 ] && [ "$r" -le 5412 ]; }; then
        echo "catII"
    else
        echo "catIII"
    fi
}

echo "======================================================================"
echo " Time-Walk Calibration Status"
echo " Input ROOT runs: ${IN_DIR}"
echo " Output JSONs:    ${OUT_DIR}"
echo "======================================================================"

declare -A TOTAL_RUNS
declare -A FITTED_RUNS
MISSING_RUNS=()

TOTAL_RUNS["catI"]=0; TOTAL_RUNS["catII"]=0; TOTAL_RUNS["catIII"]=0; TOTAL_RUNS["all"]=0
FITTED_RUNS["catI"]=0; FITTED_RUNS["catII"]=0; FITTED_RUNS["catIII"]=0; FITTED_RUNS["all"]=0

for f in $(ls -1 "${IN_DIR}"/run*.root 2>/dev/null | sort -V); do
    r=$(basename "$f" | sed -E 's/run([0-9]+)\.root/\1/')
    if [[ ! "$r" =~ ^[0-9]+$ ]]; then continue; fi

    cat=$(get_cat "$r")
    TOTAL_RUNS["$cat"]=$((TOTAL_RUNS["$cat"] + 1))
    TOTAL_RUNS["all"]=$((TOTAL_RUNS["all"] + 1))

    json="${OUT_DIR}/run${r}_timing_calibration.json"
    if [ -f "$json" ] && [ $(stat -c%s "$json" 2>/dev/null || echo 0) -gt 500 ]; then
        FITTED_RUNS["$cat"]=$((FITTED_RUNS["$cat"] + 1))
        FITTED_RUNS["all"]=$((FITTED_RUNS["all"] + 1))
    else
        MISSING_RUNS+=("$r ($cat)")
    fi
done

printf "%-12s | %-12s | %-12s | %-10s\n" "Category" "Total Runs" "Fitted JSON" "Progress"
echo "------------------------------------------------------------"
for c in catI catII catIII all; do
    tot=${TOTAL_RUNS["$c"]}
    fit=${FITTED_RUNS["$c"]}
    pct="0.0%"
    if [ "$tot" -gt 0 ]; then
        pct=$(awk "BEGIN {printf \"%.1f%%\", ($fit/$tot)*100}")
    fi
    printf "%-12s | %-12d | %-12d | %-10s\n" "$c" "$tot" "$fit" "$pct"
done

if [ ${#MISSING_RUNS[@]} -gt 0 ]; then
    echo "------------------------------------------------------------"
    echo " Missing Fits (${#MISSING_RUNS[@]} runs):"
    printf '%s\n' "${MISSING_RUNS[@]}" | paste - - - - | column -t
fi
echo "======================================================================"
