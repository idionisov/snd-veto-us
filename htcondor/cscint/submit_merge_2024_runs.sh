#!/bin/bash
# ==============================================================================
# Submit 2024 Run Partition Merges to HTCondor (10 jobs, 1 job per run)
# Flavour: workday, 4 CPUs, 8GB RAM, Force Overwrite: 1
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

mkdir -p out err log /eos/user/i/idioniso/Timing/cscint/runs

ARGS_FILE="${DIR}/args_merge_catIII_2024.txt"
N_RUNS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting 2024 cscint Run Merging Jobs to HTCondor"
echo " Runs:        ${N_RUNS} runs (8638, 8724, 9094, 9269, 9361, 9436, 9622, 9649, 9685, 9880)"
echo " Flavour:     workday"
echo " CPUs/Job:    4 CPUs (hadd -j 4)"
echo " Memory/Job:  8GB"
echo " Force:       1 (cleanly overwrites/restarts)"
echo " Destination: /eos/user/i/idioniso/Timing/cscint/runs/run<RUN>.root"
echo " Time:        $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

condor_submit merge_runs.sub \
    args_file="${ARGS_FILE}" \
    flavour="workday" \
    force=1 \
    "$@"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_RUNS} jobs. Monitor with: condor_q"
echo "======================================================================"
