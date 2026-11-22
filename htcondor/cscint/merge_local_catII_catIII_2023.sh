#!/bin/bash
set -eo pipefail

# ==============================================================================
# Local Parallel Merger for Cat II and Cat III (2023 only)
# Usage: ./merge_local_catII_catIII_2023.sh [N_JOBS]
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/sndswEnv.sh"

N_JOBS="${1:-8}"
ARGS_FILE="${DIR}/args_merge_runs_catII_catIII_2023.txt"
WORKER="${DIR}/run_merge_run_worker.sh"

echo "======================================================================"
echo " Step 1: Merging 43 runs into /eos/user/i/idioniso/Timing/cscint/runs/"
echo " Parallel processes: ${N_JOBS}"
echo "======================================================================"

xargs -a "${ARGS_FILE}" -n 2 -P "${N_JOBS}" bash -c '
    run="$1"
    cat="$2"
    "'"${WORKER}"'" "${run}" "${cat}"
' _

echo "======================================================================"
echo " Step 2: Merging runs into category ROOT files"
echo "======================================================================"
"${DIR}/merge_categories.sh"

echo "======================================================================"
echo " [ALL DONE] Full run files and category files merged successfully."
echo "======================================================================"
