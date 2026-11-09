#!/bin/bash

# ==============================================================================
# Helper script to monitor TimeWalk Calibration (250 Jobs) on EOS & HTCondor
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

RUN="${1:-5999}"
RUN_STR=$(printf "%06d" "${RUN}")
OUT_DIR="${2:-/eos/user/i/idioniso/Timing/run${RUN_STR}}"
PARALLEL_DIR="${OUT_DIR}/parallel_parts"
TOTAL_JOBS=250

echo "=========================================================="
echo " SND@LHC TimeWalk Parameter Extraction Status ($(date '+%Y-%m-%d %H:%M:%S'))"
echo " Run:            ${RUN}"
echo " EOS Directory:  ${PARALLEL_DIR}"
echo "=========================================================="

python3 -c "
import os, glob

base = '${PARALLEL_DIR}'
total = ${TOTAL_JOBS}

completed = []
missing = []

for j in range(total):
    pdir = os.path.join(base, f'part_{j}')
    files = glob.glob(os.path.join(pdir, 'raw_histograms_*.root'))
    valid = False
    for f in files:
        if os.path.exists(f) and os.path.getsize(f) > 10000:
            valid = True
            break
    if valid:
        completed.append(j)
    else:
        missing.append(j)

pct = len(completed) / total * 100.0
print(f'Completed Jobs on EOS : {len(completed)} / {total} ({pct:.1f}%)')
print(f'Pending / Missing Jobs: {len(missing)} / {total}')

if missing and len(missing) <= 30:
    print('Missing Job IDs: ' + ','.join(map(str, missing)))
elif missing:
    print('First 15 missing IDs: ' + ','.join(map(str, missing[:15])) + ' ...')
    print('You can resubmit missing jobs with: ./submit_pExtr.sh -j ' + ','.join(map(str, missing[:15])))

merged_root = os.path.join('${OUT_DIR}', 'merged_raw_histograms.root')
calib_json = os.path.join('${OUT_DIR}', f'run{${RUN}:06d}_timing_calibration.json')
calib_root = os.path.join('${OUT_DIR}', 'timewalk_calibration.root')

print('----------------------------------------------------------')
print(f'Merged Histograms  : {\"EXISTS\" if os.path.exists(merged_root) else \"NOT YET\"} ({merged_root})')
print(f'Final Calib JSON   : {\"EXISTS\" if os.path.exists(calib_json) else \"NOT YET\"} ({calib_json})')
print(f'Final QA ROOT File : {\"EXISTS\" if os.path.exists(calib_root) else \"NOT YET\"} ({calib_root})')
"

echo "----------------------------------------------------------"
echo "HTCondor Queue Status:"
if command -v condor_q >/dev/null 2>&1; then
    condor_q
else
    echo "  (condor_q command not available on this machine)"
fi
echo "=========================================================="
