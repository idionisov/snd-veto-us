#!/bin/bash
# ==============================================================================
# Submit All Partition Jobs for a Single Run (default: 5097)
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

RUN="${1:-5097}"
FLAVOUR="${2:-workday}"
shift 2 2>/dev/null || shift $# 2>/dev/null || true

ARGS_RUN="${DIR}/args_run${RUN}.txt"

# 1. Generate or extract partition list for the target run
if grep -q "^${RUN} " "${DIR}/args_partitions_all.txt" 2>/dev/null; then
    grep "^${RUN} " "${DIR}/args_partitions_all.txt" > "${ARGS_RUN}"
else
    source "${DIR}/sndswEnv.sh" 2>/dev/null || true
    python3 -c "
import os, glob, re, sys
sys.path.insert(0, '/afs/cern.ch/work/i/idioniso/snd-veto-us')
from scripts.sipm_ref_diff import get_run_category
cat = get_run_category(${RUN})
run_dir = f'/eos/experiment/sndlhc/convertedData/physics/2022/run_{${RUN}:06d}'
if not os.path.exists(run_dir):
    for yr in ['2023', '2024', '2025', '2026']:
        cand = f'/eos/experiment/sndlhc/convertedData/physics/{yr}/run_{${RUN}:06d}'
        if os.path.exists(cand):
            run_dir = cand
            break
raw_files = glob.glob(os.path.join(run_dir, 'sndsw_raw-*.root'))
parts = sorted([int(re.search(r'sndsw_raw-(\d+)\.root', f).group(1)) for f in raw_files if re.search(r'sndsw_raw-(\d+)\.root', f)])
for p in parts:
    print(f'${RUN} {p} {cat}')
" > "${ARGS_RUN}"
fi

N_PARTS=$(wc -l < "${ARGS_RUN}" 2>/dev/null || echo 0)
if [ "${N_PARTS}" -eq 0 ]; then
    echo "[ERROR] No partitions found for Run ${RUN}!" >&2
    exit 1
fi

echo "======================================================================"
echo " Submitting Partition Jobs for Run ${RUN}"
echo " Partitions: ${N_PARTS} jobs"
echo " Flavour:    ${FLAVOUR}"
echo " Arguments:  ${ARGS_RUN}"
echo "======================================================================"

condor_submit cscint.sub \
    args_file="${ARGS_RUN}" \
    flavour="${FLAVOUR}" \
    "$@"
