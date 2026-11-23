#!/bin/bash
# ==============================================================================
# Submit 2024 Time-Walk Run Partition Merges to HTCondor (10 jobs, 1 per run)
# Flavour: workday, 4 CPUs, 8GB RAM, 10GB disk, Force Overwrite: 1
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${DIR}/submit_merge_runs.sh" 2024 "$@"
