#!/bin/bash
# ==============================================================================
# Submit Only Missing/Incomplete cscint Fit Jobs to HTCondor (36 runs)
# ==============================================================================
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${DIR}/submit_fit.sh" missing "$@"
