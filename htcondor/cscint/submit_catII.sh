#!/bin/bash
# ==============================================================================
# Submit Category II Partition Jobs for cscint (SiPM Ref Diff) Extraction
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

FLAVOUR="workday"
FORCE=0
MISSING_ONLY=0
DRY_RUN=0
ARGS_FILE="${DIR}/args_partitions_catII_max20.txt"

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  -m, --missing-only    Submit ONLY partitions not yet completed on EOS (default: submit full list)
  -f, --force           Force re-extraction of all partitions (FORCE=1)
  --flavour FLAVOUR     HTCondor JobFlavour: longlunch (2h), workday (8h, default)
  --dry-run             Show job counts and arguments without submitting
  -h, --help            Show this help message
EOF
    exit 0
}

EXTRA_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--missing-only) MISSING_ONLY=1; shift ;;
        -f|--force) FORCE=1; shift ;;
        --flavour) FLAVOUR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) EXTRA_ARGS+=("$1"); shift ;;
    esac
done

if [ "${MISSING_ONLY}" -eq 1 ]; then
    MISSING_FILE="${DIR}/args_partitions_catII_missing.txt"
    echo " ~ Scanning for missing Category II partitions on EOS..."
    python3 -c '
import os
base_dir = "'"${DIR}"'"
args_file = f"{base_dir}/args_partitions_catII.txt"
missing_file = f"{base_dir}/args_partitions_catII_missing.txt"
out_base = "/eos/user/i/idioniso/Timing/cscint_parts"

missing = []
total = 0
done = 0
with open(args_file) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        total += 1
        run, part, cat = line.split()
        target = f"{out_base}/{cat}/run{run}/part_{part}.root"
        if os.path.exists(target) and os.path.getsize(target) > 1000:
            done += 1
        else:
            missing.append(line)

with open(missing_file, "w") as out:
    for m in missing:
        out.write(m + "\n")
'
    ARGS_FILE="${MISSING_FILE}"
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")

echo "======================================================================"
echo " Submitting Category II Partition Jobs for cscint"
echo " Args File:    ${ARGS_FILE}"
echo " Total Jobs:   ${TOTAL_JOBS}"
echo " Flavour:      ${FLAVOUR}"
echo " Force:        ${FORCE}"
echo " Missing Only: ${MISSING_ONLY}"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. First 10 entries in ${ARGS_FILE}:"
    head -n 10 "${ARGS_FILE}"
    echo "[INFO] Submit skipped."
    exit 0
fi

condor_submit cscint.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}" \
    "${EXTRA_ARGS[@]}"
