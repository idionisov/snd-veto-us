#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

mkdir -p out err log /eos/user/i/idioniso/Timing/run005100/parallel_parts

DAG_FILE="${SCRIPT_DIR}/run5100_pipeline.dag"

echo "=========================================================="
echo " Submitting Run 5100 Full Calibration DAGMan Workflow"
echo " DAG File  : ${DAG_FILE}"
echo " Total     : 2 Stages, 502 total HTCondor executions"
echo " Mode      : Fully Automated End-to-End Pipeline"
echo "=========================================================="

if [ "$1" = "--dry-run" ]; then
    echo "[Dry-Run Mode] Command that would be executed on lxplus:"
    echo "condor_submit_dag ${DAG_FILE}"
    exit 0
fi

if ! command -v condor_submit_dag >/dev/null 2>&1; then
    echo "ERROR: 'condor_submit_dag' not found in PATH." >&2
    echo "Please execute this script from an lxplus node (e.g., ssh lxplus.cern.ch)." >&2
    exit 1
fi

condor_submit_dag "${DAG_FILE}"

echo ""
echo "DAG submitted! You can monitor the workflow with:"
echo "  condor_q -dag"
echo "  tail -f ${DAG_FILE}.dagman.out"
