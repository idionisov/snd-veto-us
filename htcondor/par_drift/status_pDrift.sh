#!/bin/bash

# ==============================================================================
# Helper script to monitor TimeWalk Run Drift Study on EOS & HTCondor
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

BASE_DIR="/eos/user/i/idioniso/Timing"

echo "=========================================================="
echo " SND@LHC TimeWalk Run Drift Study Status ($(date '+%Y-%m-%d %H:%M:%S'))"
echo " Destination: ${BASE_DIR}"
echo "=========================================================="

python3 -c "
import os

base = '${BASE_DIR}'

def check_category(cat_name, args_path):
    if not os.path.exists(args_path):
        print(f'{cat_name}: {args_path} not found.')
        return
    with open(args_path, 'r') as f:
        runs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
    
    completed = []
    missing = []
    for r in runs:
        r_str = f'run{int(r):06d}'
        json_path = os.path.join(base, r_str, f'{r_str}_timing_calibration.json')
        root_path = os.path.join(base, r_str, 'timewalk_calibration.root')
        if os.path.exists(json_path) and os.path.exists(root_path) and os.path.getsize(root_path) > 50000:
            completed.append(r)
        else:
            missing.append(r)
    
    total = len(runs)
    pct = len(completed) / total * 100.0 if total > 0 else 0.0
    print(f'=== {cat_name} ({total} Runs) ===')
    print(f'  Completed on EOS : {len(completed)} / {total} ({pct:.1f}%)')
    print(f'  Pending / Missing: {len(missing)} / {total}')
    if missing and len(missing) <= 20:
        print('  Missing Runs: ' + ','.join(missing))
    elif missing:
        print('  First 10 missing: ' + ','.join(missing[:10]) + ' ...')

check_category('Category I (>3M entries)', '${SCRIPT_DIR}/args_run_catI.txt')
print('')
check_category('Category II (>3M entries)', '${SCRIPT_DIR}/args_run_catII.txt')
"

echo "----------------------------------------------------------"
echo "HTCondor Queue Status:"
if command -v condor_q >/dev/null 2>&1; then
    condor_q
else
    echo "  (condor_q command not available on this machine)"
fi
echo "=========================================================="
