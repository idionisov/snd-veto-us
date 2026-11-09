#!/bin/bash
set -eo pipefail

# ==============================================================================
# HTCondor Submission for TimeWalk Run Drift Study (1 Job per Run)
#
# Usage:
#   ./submit_pDrift.sh --cat 1         # Submit all Category I runs (>3M entries, 89 runs)
#   ./submit_pDrift.sh --cat 2         # Submit all Category II runs (>3M entries, 33 runs)
#   ./submit_pDrift.sh -r 4427,4449    # Submit specific runs
#   ./submit_pDrift.sh -n 10000        # Override event count per run
#   ./submit_pDrift.sh -f workday      # Set flavour (default: workday)
#   ./submit_pDrift.sh --dry-run       # Dry run check
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

mkdir -p out err log

DEFAULT_CAT1="${SCRIPT_DIR}/args_run_catI.txt"
DEFAULT_CAT2="${SCRIPT_DIR}/args_run_catII.txt"
ARGS_FILE="${DEFAULT_CAT1}"
TMP_ARGS=""
FLAVOUR="testmatch"
FORCE="0"
DRY_RUN="0"
N_EVENTS="10000000"
SPEED_EVENTS="10000000"
OUT_BASE="/eos/user/i/idioniso/Timing"
REFERENCESYSTEM="0"
CAT_LABEL="Category I"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --cat|--category)
      CAT_ARG="$2"
      if [ "${CAT_ARG}" = "1" ] || [ "${CAT_ARG}" = "I" ] || [ "${CAT_ARG}" = "i" ]; then
          ARGS_FILE="${DEFAULT_CAT1}"
          CAT_LABEL="Category I"
      elif [ "${CAT_ARG}" = "2" ] || [ "${CAT_ARG}" = "II" ] || [ "${CAT_ARG}" = "ii" ]; then
          ARGS_FILE="${DEFAULT_CAT2}"
          CAT_LABEL="Category II"
      else
          echo "[ERROR] Invalid category '${CAT_ARG}'. Use 1 (I) or 2 (II)." >&2
          exit 1
      fi
      shift 2
      ;;
    -a|--args-file)
      ARGS_FILE="$2"
      CAT_LABEL="Custom"
      shift 2
      ;;
    -f|--flavour)
      FLAVOUR="$2"
      shift 2
      ;;
    -n|--n-events)
      N_EVENTS="$2"
      shift 2
      ;;
    -o|--out-base)
      OUT_BASE="$2"
      shift 2
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -r|--runs)
      RUN_ARG="$2"
      shift 2
      TMP_ARGS=$(mktemp /tmp/drift_runs_XXXXXX.txt)
      if [[ "${RUN_ARG}" =~ ^[0-9]+-[0-9]+$ ]]; then
          R_START=$(echo "${RUN_ARG}" | cut -d'-' -f1)
          R_END=$(echo "${RUN_ARG}" | cut -d'-' -f2)
          # Filter from existing list
          awk -v s="${R_START}" -v e="${R_END}" '$1 >= s && $1 <= e' "${ARGS_FILE}" > "${TMP_ARGS}"
      else
          IFS=',' read -ra ADDR <<< "${RUN_ARG}"
          for r in "${ADDR[@]}"; do
              echo "${r}" >> "${TMP_ARGS}"
          done
      fi
      ARGS_FILE="${TMP_ARGS}"
      CAT_LABEL="Subset (${RUN_ARG})"
      ;;
    *)
      if [ -f "$1" ]; then
          ARGS_FILE="$1"
          CAT_LABEL="Custom ($1)"
          shift
      else
          shift
      fi
      ;;
  esac
done

trap '[ -n "${TMP_ARGS}" ] && rm -f "${TMP_ARGS}"' EXIT

TOTAL_RUNS=$(wc -l < "${ARGS_FILE}")
echo "=========================================================="
echo " Submitting TimeWalk Run Drift Study to HTCondor"
echo " Selection      : ${CAT_LABEL}"
echo " Total Runs/Jobs: ${TOTAL_RUNS}"
echo " Events per Run : ${N_EVENTS}"
echo " Job Flavour    : ${FLAVOUR}"
echo " Force Mode     : ${FORCE}"
echo " Base Out Dir   : ${OUT_BASE}"
echo " Args File      : ${ARGS_FILE}"
echo "=========================================================="

if [ "${DRY_RUN}" = "1" ]; then
    echo "[Dry-Run Mode] Command that would be executed:"
    echo "condor_submit par_drift.sub args_file=\"${ARGS_FILE}\" flavour=\"${FLAVOUR}\" force=\"${FORCE}\" n_events=\"${N_EVENTS}\" out_base=\"${OUT_BASE}\" ref_sys=\"${REFERENCESYSTEM}\""
    exit 0
fi

if ! command -v condor_submit >/dev/null 2>&1; then
    echo "ERROR: 'condor_submit' not found in PATH." >&2
    echo "Please run this script from an lxplus node (e.g., ssh lxplus.cern.ch)." >&2
    exit 1
fi

condor_submit par_drift.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}" \
    n_events="${N_EVENTS}" \
    speed_events="${SPEED_EVENTS}" \
    out_base="${OUT_BASE}" \
    ref_sys="${REFERENCESYSTEM}"

echo ""
echo "Jobs submitted! You can monitor them using:"
echo "  ./status_pDrift.sh"
