#!/bin/bash
set -eo pipefail

# ==============================================================================
# HTCondor Submission for TimeWalk Parameter Extraction (Run 5097, 250 Jobs)
#
# Usage:
#   ./submit_pExtr.sh                 # Submit all 250 jobs
#   ./submit_pExtr.sh -j 0-9          # Submit jobs 0 to 9 for testing
#   ./submit_pExtr.sh -j 0,5,10       # Submit specific job IDs
#   ./submit_pExtr.sh -f longlunch    # Use longlunch flavour (default: workday)
#   ./submit_pExtr.sh --step1         # Run single-core Step 1 (c_scint speed extraction)
#   ./submit_pExtr.sh --merge         # Merge all completed raw histograms
#   ./submit_pExtr.sh --fit           # Run final fit on merged histograms
#   ./submit_pExtr.sh --dry-run       # Dry-run mode
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

mkdir -p out err log

RUN="5097"
RUN_STR=$(printf "%06d" "${RUN}")
OUT_DIR="/eos/user/i/idioniso/Timing/run${RUN_STR}"
REFERENCESYSTEM="0"
DEFAULT_ARGS="${SCRIPT_DIR}/args_run5097_250jobs.txt"
ARGS_FILE="${DEFAULT_ARGS}"
TMP_ARGS=""
FLAVOUR="workday"
FORCE="0"
DRY_RUN="0"
DO_STEP1="0"
DO_MERGE="0"
DO_FIT="0"
POSITIONAL=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--args-file)
      ARGS_FILE="$2"
      shift 2
      ;;
    -f|--flavour)
      FLAVOUR="$2"
      shift 2
      ;;
    -r|--run)
      RUN="$2"
      RUN_STR=$(printf "%06d" "${RUN}")
      OUT_DIR="/eos/user/i/idioniso/Timing/run${RUN_STR}"
      shift 2
      ;;
    -o|--out-dir)
      OUT_DIR="$2"
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
    --step1)
      DO_STEP1="1"
      shift
      ;;
    --merge)
      DO_MERGE="1"
      shift
      ;;
    --fit)
      DO_FIT="1"
      shift
      ;;
    -j|--jobs)
      JOB_ARG="$2"
      shift 2
      TMP_ARGS=$(mktemp /tmp/tw_args_XXXXXX.txt)
      if [[ "${JOB_ARG}" =~ ^[0-9]+-[0-9]+$ ]]; then
          J_START=$(echo "${JOB_ARG}" | cut -d'-' -f1)
          J_END=$(echo "${JOB_ARG}" | cut -d'-' -f2)
          awk -v s="${J_START}" -v e="${J_END}" '$1 >= s && $1 <= e' "${DEFAULT_ARGS}" > "${TMP_ARGS}"
      else
          IFS=',' read -ra ADDR <<< "${JOB_ARG}"
          for id in "${ADDR[@]}"; do
              awk -v target="${id}" '$1 == target' "${DEFAULT_ARGS}" >> "${TMP_ARGS}"
          done
      fi
      ARGS_FILE="${TMP_ARGS}"
      ;;
    *)
      if [ -f "$1" ]; then
          ARGS_FILE="$1"
          shift
      else
          POSITIONAL+=("$1")
          shift
      fi
      ;;
  esac
done

trap '[ -n "${TMP_ARGS}" ] && rm -f "${TMP_ARGS}"' EXIT

mkdir -p "${OUT_DIR}/parallel_parts"

# ------------------------------------------------------------------------------
# STEP 1 Execution (if requested)
# ------------------------------------------------------------------------------
CSCINT_FILE="${OUT_DIR}/run${RUN_STR}_cscintvalues.json"
PY_RUN="/afs/cern.ch/user/i/idioniso/snd_master/sndsw/shipLHC/scripts/run_TimeWalk.py"

if [ "${DO_STEP1}" = "1" ]; then
    echo "=========================================================="
    echo " Running Step 1: c_scint Speed Extraction for Run ${RUN}"
    echo " Output: ${CSCINT_FILE}"
    echo "=========================================================="
    if [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
        source "${SCRIPT_DIR}/sndswEnv.sh"
    fi
    python3 -X faulthandler "${PY_RUN}" \
        -r "${RUN}" \
        -s 0 \
        -n 2000000 \
        --speedEvents 2000000 \
        --speedOnly \
        --referencesystem "${REFERENCESYSTEM}" \
        -o "${OUT_DIR}"
    echo "[STEP 1] Finished: ${CSCINT_FILE}"
    exit 0
fi

# ------------------------------------------------------------------------------
# MERGE Execution (if requested)
# ------------------------------------------------------------------------------
if [ "${DO_MERGE}" = "1" ]; then
    "${SCRIPT_DIR}/merge_and_fit.sh" -r "${RUN}" --merge
    exit 0
fi

# ------------------------------------------------------------------------------
# FIT Execution (if requested)
# ------------------------------------------------------------------------------
if [ "${DO_FIT}" = "1" ]; then
    "${SCRIPT_DIR}/merge_and_fit.sh" -r "${RUN}" --fit
    exit 0
fi

# ------------------------------------------------------------------------------
# Check for c_scint speed calibration file before batch submission
# ------------------------------------------------------------------------------
if [ ! -f "${CSCINT_FILE}" ]; then
    echo "[WARNING] Precomputed c_scint file not found: ${CSCINT_FILE}"
    echo "It is recommended to run Step 1 once beforehand using:"
    echo "  ./submit_pExtr.sh --step1"
    echo ""
    if [ "${DRY_RUN}" != "1" ] && [ -t 0 ]; then
        read -p "Do you want to proceed with batch submission anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborting."
            exit 1
        fi
    fi
fi

TOTAL_JOBS=$(wc -l < "${ARGS_FILE}")
echo "=========================================================="
echo " Submitting TimeWalk Calibration (${TOTAL_JOBS} Jobs) to HTCondor"
echo " Run Number     : ${RUN}"
echo " Total Jobs     : ${TOTAL_JOBS}"
echo " Job Flavour    : ${FLAVOUR}"
echo " Force Mode     : ${FORCE}"
echo " Output Dir     : ${OUT_DIR}"
echo " Args File      : ${ARGS_FILE}"
echo "=========================================================="

if [ "${DRY_RUN}" = "1" ]; then
    echo "[Dry-Run Mode] Command that would be executed:"
    echo "condor_submit par_extraction.sub args_file=\"${ARGS_FILE}\" flavour=\"${FLAVOUR}\" force=\"${FORCE}\" run=\"${RUN}\" out_dir=\"${OUT_DIR}\" ref_sys=\"${REFERENCESYSTEM}\""
    exit 0
fi

if ! command -v condor_submit >/dev/null 2>&1; then
    echo "ERROR: 'condor_submit' not found in PATH." >&2
    echo "Please run this script from an lxplus node (e.g., ssh lxplus.cern.ch)." >&2
    exit 1
fi

condor_submit par_extraction.sub \
    args_file="${ARGS_FILE}" \
    flavour="${FLAVOUR}" \
    force="${FORCE}" \
    run="${RUN}" \
    out_dir="${OUT_DIR}" \
    ref_sys="${REFERENCESYSTEM}"

echo ""
echo "Jobs submitted! You can monitor them using:"
echo "  ./status_pExtr.sh"
echo "Once all jobs complete, run the merger and final fit with:"
echo "  ./merge_and_fit.sh"
