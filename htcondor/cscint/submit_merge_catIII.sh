#!/bin/bash
# ==============================================================================
# Submit Category III Merging Workflow via HTCondor DAGMan
#
# Usage:
#   ./submit_merge_catIII.sh 2023   # Merge 2023 runs -> catIII_2023.root
#   ./submit_merge_catIII.sh 2024   # Merge 2024 runs -> catIII_2024.root
#   ./submit_merge_catIII.sh 2025   # Merge 2025 runs -> catIII_2025.root
#   ./submit_merge_catIII.sh 2026   # Merge 2026 runs -> catIII_2026.root
#   ./submit_merge_catIII.sh all    # Merge all 40 Cat III runs -> all 4 year files
#
# Options:
#   FORCE=1 ./submit_merge_catIII.sh 2024   # Force re-merging existing runs
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="${1:-all}"

if [[ ! "${TARGET}" =~ ^(2023|2024|2025|2026|all)$ ]]; then
    echo "Usage: $0 [2023|2024|2025|2026|all]" >&2
    exit 1
fi

DAG_FILE="${DIR}/merge_catIII_${TARGET}.dag"

if [ ! -f "${DAG_FILE}" ]; then
    echo "[ERROR] DAG file not found: ${DAG_FILE}" >&2
    exit 1
fi

echo "======================================================================"
echo " Submitting Category III Merge Workflow for: ${TARGET}"
echo " DAG File: ${DAG_FILE}"
echo " Force:    ${FORCE:-1}"
echo " Time:     $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

condor_submit_dag -force "${DAG_FILE}"

echo "======================================================================"
echo "[SUCCESS] Workflow submitted. Monitor with: condor_q"
echo "======================================================================"
