#!/bin/bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="${FLAVOUR:-workday}"
FORCE_FLAG="${FORCE:-0}"
ARGS_FILE="${DIR}/args_run5408_10p.txt"

echo "======================================================================"
echo " Submitting Run 5408 (10 partitions, 10M events) for Time-Walk"
echo " Total jobs: $(wc -l < "${ARGS_FILE}")"
echo " Args File:  ${ARGS_FILE}"
echo " Flavour:    ${FLAVOUR}"
echo " Force:      ${FORCE_FLAG}"
echo "======================================================================"

condor_submit timewalk.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE_FLAG}" \
    "$@"
