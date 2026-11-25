#!/bin/bash
# ==============================================================================
# Submit Time-Walk HTCondor DAGMan Workflows (Fill -> Merge -> Fit)
# ==============================================================================
set -eo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${DIR}"

TARGET="${1:-catII}"
shift || true

MAX_JOBS=1000
DRY_RUN=0

usage() {
    cat <<EOF
Usage: $0 [TARGET] [options]

Targets:
  catII | 2022           Submit Cat II 2022 DAG (33 runs, 1,478 partition jobs)
  2023  | catIII_2023    Submit Cat III 2023 DAG (10 runs, 500 partition jobs)
  2024  | catIII_2024    Submit Cat III 2024 DAG (10 runs, 500 partition jobs)
  2025  | catIII_2025    Submit Cat III 2025 DAG (10 runs, 500 partition jobs)
  2026  | catIII_2026    Submit Cat III 2026 DAG (10 runs, 500 partition jobs)
  all                    Submit all 73 runs across 2022-2026 (3,478 partition jobs)

Options:
  -m, --maxjobs N        Max concurrent jobs submitted to HTCondor (default: ${MAX_JOBS})
  --dry-run              Inspect DAG structure without submitting
  -h, --help             Show this help
EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--maxjobs) MAX_JOBS="$2"; shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) usage ;;
        *) echo "[ERROR] Unknown option: $1" >&2; exit 1 ;;
    esac
done

mkdir -p out err log /eos/user/i/idioniso/Timing/timewalk2/parts /eos/user/i/idioniso/Timing/timewalk2/runs /eos/user/i/idioniso/Timing/timewalk2/fits /eos/user/i/idioniso/Timing/timewalk2/fits_root

case "${TARGET}" in
    catII|catii|2022)
        DAG_FILE="timewalk_catII_2022.dag"
        LABEL="Category II (2022)"
        ;;
    2023|catIII_2023)
        DAG_FILE="timewalk_catIII_2023.dag"
        LABEL="Category III (2023)"
        ;;
    2024|catIII_2024)
        DAG_FILE="timewalk_catIII_2024.dag"
        LABEL="Category III (2024)"
        ;;
    2025|catIII_2025)
        DAG_FILE="timewalk_catIII_2025.dag"
        LABEL="Category III (2025)"
        ;;
    2026|catIII_2026)
        DAG_FILE="timewalk_catIII_2026.dag"
        LABEL="Category III (2026)"
        ;;
    all|ALL)
        DAG_FILE="timewalk_all.dag"
        LABEL="All Eras (2022-2026, 73 runs)"
        ;;
    *)
        echo "[ERROR] Unknown target: '${TARGET}'. Valid targets: catII, 2023, 2024, 2025, 2026, all" >&2
        exit 1
        ;;
esac

if [ ! -f "${DAG_FILE}" ]; then
    echo "[INFO] Generating DAG files..."
    python3 generate_dag.py
fi

echo "======================================================================"
echo " Submitting HTCondor DAGMan Workflow: ${LABEL}"
echo " DAG File:     ${DAG_FILE}"
echo " Max Jobs:     ${MAX_JOBS}"
echo " Time:         $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================================"

if [ "${DRY_RUN}" -eq 1 ]; then
    echo "[INFO] Dry run requested. DAG summary:"
    head -n 25 "${DAG_FILE}"
    echo "..."
    tail -n 15 "${DAG_FILE}"
    exit 0
fi

condor_submit_dag -maxjobs "${MAX_JOBS}" "${DAG_FILE}"

echo "======================================================================"
echo "[SUCCESS] DAGMan workflow submitted: ${DAG_FILE}"
echo " Monitor queue:      condor_q -dag"
echo " Monitor DAG log:    tail -f ${DAG_FILE}.dagman.out"
echo " Status of files:    ./status_timewalk.sh && ./status_merge_runs.sh && ./status_fits.sh"
echo "======================================================================"
