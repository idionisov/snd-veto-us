#!/bin/bash
# ==============================================================================
# Helper to Run Partition Merger into reference_times_2022.root
# ==============================================================================
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${DIR}/sndswEnv.sh"

python3 -X faulthandler "${DIR}/merge_ref_times.py" "$@"
