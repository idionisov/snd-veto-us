#!/bin/bash
# ==============================================================================
# Submit 2022 Partition Jobs for cscint (max 15 partitions per run)
# Usage:
#   ./submit_top15p.sh           # Submits all (Cat I + Cat II, 1647 jobs)
#   ./submit_top15p.sh catI      # Submits Cat I (1165 jobs)
#   ./submit_top15p.sh catII     # Submits Cat II (482 jobs)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

CAT="${1:-all}"
shift || true

case "${CAT}" in
    all|ALL)
        ARGS_FILE="${DIR}/args_partitions_all_max15.txt"
        TITLE="ALL (Cat I + Cat II, max 15 partitions/run)"
        ;;
    catI|cati|CATI|I)
        ARGS_FILE="${DIR}/args_partitions_catI_max15.txt"
        TITLE="Category I (max 15 partitions/run)"
        ;;
    catII|catii|CATII|II)
        ARGS_FILE="${DIR}/args_partitions_catII_max15.txt"
        TITLE="Category II (max 15 partitions/run)"
        ;;
    *)
        echo "Unknown category: ${CAT}. Choose: all, catI, or catII." >&2
        exit 1
        ;;
esac

if [ ! -f "${ARGS_FILE}" ]; then
    echo "[INFO] ${ARGS_FILE} not found. Generating now..."
    python3 "${DIR}/generate_args.py" -p 15 --from-existing
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Partition Jobs for cscint: ${TITLE}"
echo " Arguments : ${ARGS_FILE}"
echo " Total jobs: ${TOTAL_JOBS}"
echo " Flavour   : workday"
echo "======================================================================"

condor_submit cscint.sub \
    args_file="${ARGS_FILE}" \
    flavour="workday" \
    "$@"
