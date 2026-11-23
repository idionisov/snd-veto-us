#!/bin/bash
# ==============================================================================
# Submit HTCondor Jobs to Merge Time-Walk Partitions into Run ROOT Files
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="catII"
FLAVOUR="workday"
FORCE=1
DRY_RUN=0
SPECIFIC_RUN=""

# Parse positional target if given first
if [[ $# -gt 0 ]] && [[ "$1" =~ ^(catII|catIII|2023|2025|2026|catIII_2023|catIII_2025|catIII_2026|all)$ ]]; then
    TARGET="$1"
    shift
fi

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  catII                   Merge all 33 Category II runs (default)
  2023 | catIII_2023      Merge 10 Category III 2023 runs
  2025 | catIII_2025      Merge 10 Category III 2025 runs
  2026 | catIII_2026      Merge 10 Category III 2026 runs
  catIII                  Merge all 30 Category III runs (2023, 2025, 2026)
  all                     Merge all 63 runs across Cat II & Cat III

Options:
  -r, --run RUN           Submit a single specific run number
  -f, --force             Force overwrite of existing run files (default: 1)
  --no-force              Skip runs if output file already exists
  --flavour FLAVOUR       HTCondor flavour (default: workday)
  --dry-run               Display jobs without submitting
  -h, --help              Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        catII|catIII|2023|2025|2026|catIII_2023|catIII_2025|catIII_2026|all)
            TARGET="$1"; shift ;;
        -r|--run) SPECIFIC_RUN="$2"; shift 2 ;;
        -f|--force) FORCE=1; shift ;;
        --no-force) FORCE=0; shift ;;
        --flavour) FLAVOUR="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p out err log /eos/user/i/idioniso/Timing/timewalk/runs

case "${TARGET}" in
    catII|catii|CATII|II)
        ARGS_FILE="${DIR}/args_merge_runs_catII.txt"
        ;;
    2023|catIII_2023)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2023.txt"
        ;;
    2025|catIII_2025)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2025.txt"
        ;;
    2026|catIII_2026)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_2026.txt"
        ;;
    catIII|catiii|CATIII|III)
        ARGS_FILE="${DIR}/args_merge_runs_catIII_all.txt"
        ;;
    all|ALL)
        ARGS_FILE="${DIR}/args_merge_runs_all.txt"
        ;;
    *)
        echo "[ERROR] Unknown target: '${TARGET}'. Valid options: catII, 2023, 2025, 2026, catIII, all" >&2
        exit 1
        ;;
esac

SUBMIT_ARGS="${ARGS_FILE}"
if [ -n "${SPECIFIC_RUN}" ]; then
    TMP_ARGS="${DIR}/args_custom_merge_$$.txt"
    grep -E "^${SPECIFIC_RUN}[[:space:]]" "${DIR}/args_merge_runs_all.txt" > "${TMP_ARGS}" || {
        echo "[ERROR] Run ${SPECIFIC_RUN} not found in candidate list!" >&2
        rm -f "${TMP_ARGS}"
        exit 1
    }
    SUBMIT_ARGS="${TMP_ARGS}"
    trap 'rm -f "${TMP_ARGS}"' EXIT
fi

N_RUNS=$(wc -l < "${SUBMIT_ARGS}")
echo "======================================================================"
echo " Submitting Time-Walk Run Merging Jobs to HTCondor"
echo " Target Group: ${TARGET}"
echo " Total Runs:   ${N_RUNS}"
echo " Job Flavour:  ${FLAVOUR}"
echo " Force Overwrite: FORCE=${FORCE}"
echo " Args File:    ${SUBMIT_ARGS}"
echo " Time:         $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. Runs queued:"
    cat "${SUBMIT_ARGS}"
    exit 0
fi

condor_submit merge_runs.sub \
    args_file="${SUBMIT_ARGS}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}"

echo "======================================================================"
echo "[SUCCESS] Submitted ${N_RUNS} run merge jobs. Monitor with: condor_q"
echo " Destination: /eos/user/i/idioniso/Timing/timewalk/runs/run<RUN>.root"
echo "======================================================================"
