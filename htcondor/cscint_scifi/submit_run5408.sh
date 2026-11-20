#!/bin/bash
# ==============================================================================
# Submit All Partition Jobs for Run 5408
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

RUN="5408"
FLAVOUR="${1:-workday}"
shift 1 2>/dev/null || shift $# 2>/dev/null || true

ARGS_RUN="${DIR}/args_run${RUN}.txt"

if [ ! -s "${ARGS_RUN}" ]; then
    echo "[ERROR] Argument file ${ARGS_RUN} not found or empty!" >&2
    exit 1
fi

N_PARTS=$(wc -l < "${ARGS_RUN}")

echo "======================================================================"
echo " Submitting SciFi Cluster Ref Diff (cscint_scifi) for Run ${RUN}"
echo " Partitions: ${N_PARTS} jobs (1 job per partition)"
echo " Flavour:    ${FLAVOUR}"
echo " Arguments:  ${ARGS_RUN}"
echo "======================================================================"

condor_submit cscint_scifi.sub \
    args_file="${ARGS_RUN}" \
    flavour="${FLAVOUR}" \
    "$@"
