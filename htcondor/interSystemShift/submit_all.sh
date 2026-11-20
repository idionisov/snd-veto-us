#!/bin/bash
# ==============================================================================
# Master Submission Script: All Categories (Inter-System Shift Extraction)
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

echo "======================================================================"
echo " Submitting All Categories for Inter-System Shift Extraction"
echo "======================================================================"

./submit_catII.sh "$@"
./submit_catIII_2023.sh "$@"
./submit_catIII_2024.sh "$@"
./submit_catIII_2025.sh "$@"
./submit_catIII_2026.sh "$@"

echo "======================================================================"
echo "[SUCCESS] All submission queues launched!"
echo "======================================================================"
