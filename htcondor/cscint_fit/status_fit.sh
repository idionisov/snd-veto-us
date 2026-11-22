#!/bin/bash
# ==============================================================================
# Monitor Status of cscint_fit Jobs & Output Files
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JSON_DIR="/eos/user/i/idioniso/Timing/timewalk/fits"
ROOT_DIR="/eos/user/i/idioniso/Timing/timewalk/fits_root"
ARGS_FILE="${DIR}/args_catII.txt"

echo "======================================================================"
echo " HTCondor Queue Status"
echo "======================================================================"
condor_q -nobatch 2>/dev/null | grep -E "fit_run|ID" | head -n 35 || condor_q

echo ""
echo "======================================================================"
echo " Category II Fit Outputs Status"
echo " JSON Target Directory: ${JSON_DIR}"
echo " ROOT Target Directory: ${ROOT_DIR}"
echo "======================================================================"

TOTAL=0
JSON_OK=0
ROOT_OK=0
BOTH_OK=0
MISSING=()

while read -r r; do
    [ -z "$r" ] && continue
    TOTAL=$((TOTAL + 1))
    
    jf="${JSON_DIR}/run${r}_timing_calibration.json"
    rf="${ROOT_DIR}/run${r}.root"

    has_j=0
    has_r=0

    if [ -f "$jf" ] && [ $(stat -c%s "$jf" 2>/dev/null || echo 0) -gt 1000 ]; then
        has_j=1
        JSON_OK=$((JSON_OK + 1))
    fi

    if [ -f "$rf" ] && [ $(stat -c%s "$rf" 2>/dev/null || echo 0) -gt 1000000 ]; then
        has_r=1
        ROOT_OK=$((ROOT_OK + 1))
    fi

    if [ "$has_j" -eq 1 ] && [ "$has_r" -eq 1 ]; then
        BOTH_OK=$((BOTH_OK + 1))
    else
        status_str="JSON: $([ $has_j -eq 1 ] && echo 'OK' || echo 'MISSING'), ROOT: $([ $has_r -eq 1 ] && echo 'OK' || echo 'MISSING')"
        MISSING+=("Run $r ($status_str)")
    fi
done < "${ARGS_FILE}"

printf "%-15s | %-12s | %-12s | %-12s\n" "Total Cat II" "JSONs Ready" "ROOTs Ready" "Fully Done"
echo "------------------------------------------------------------"
printf "%-15d | %-12d | %-12d | %-12d\n" "$TOTAL" "$JSON_OK" "$ROOT_OK" "$BOTH_OK"

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "------------------------------------------------------------"
    echo " Incomplete / Missing Runs (${#MISSING[@]}):"
    printf '  * %s\n' "${MISSING[@]}"
else
    echo "------------------------------------------------------------"
    echo " All ${TOTAL} Category II runs are fully fitted and verified!"
fi
echo "======================================================================"
