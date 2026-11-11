#!/bin/bash
set -eo pipefail

# ==============================================================================
# Merge Partition Histograms for cscint (SiPM Ref Diff):
#   1. Merges all partition histograms of each run into a single run ROOT file
#      with all histograms added:
#        <out_dir>/runs/run<RUN>.root
#   2. Merges all runs of each category into one unified category ROOT file:
#        <out_dir>/categories/<category>.root
# ==============================================================================

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${DIR}/sndswEnv.sh" ]; then
    source "${DIR}/sndswEnv.sh"
elif [ -f "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh" ]; then
    source "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh"
fi

IN_BASE="/eos/user/i/idioniso/Timing/cscint_parts"
OUT_BASE="/eos/user/i/idioniso/Timing/cscint"
CATEGORY="all"
SPECIFIC_RUN=""
FORCE=0
N_JOBS=8

usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -i, --input <dir>     Input directory with partition files (default: ${IN_BASE})"
    echo "  -o, --output <dir>    Output directory for runs and categories (default: ${OUT_BASE})"
    echo "  -c, --category <cat>  Category to merge (catI, catII, or all; default: all)"
    echo "  -r, --run <run>       Merge only a specific run number (optional)"
    echo "  -j, --jobs <N>        Number of parallel hadd processes (default: ${N_JOBS})"
    echo "  -f, --force           Force re-merging existing run and category files"
    echo "  -h, --help            Show this help"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--input) IN_BASE="$2"; shift 2 ;;
        -o|--output) OUT_BASE="$2"; shift 2 ;;
        -c|--category) CATEGORY="$2"; shift 2 ;;
        -r|--run) SPECIFIC_RUN="$2"; shift 2 ;;
        -j|--jobs) N_JOBS="$2"; shift 2 ;;
        -f|--force) FORCE=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown argument: $1" >&2; usage ;;
    esac
done

OUT_RUNS="${OUT_BASE}/runs"
OUT_CATS="${OUT_BASE}/categories"
mkdir -p "${OUT_RUNS}" "${OUT_CATS}"

CATS_TO_PROCESS=()
if [ "${CATEGORY}" = "all" ]; then
    CATS_TO_PROCESS=("catI" "catII")
else
    CATS_TO_PROCESS=("${CATEGORY}")
fi

echo "======================================================================"
echo " SND@LHC cscint (SiPM Ref Diff) Histogram Merger"
echo " Input Partitions : ${IN_BASE}"
echo " Output Runs      : ${OUT_RUNS}/run<RUN>.root"
echo " Output Categories: ${OUT_CATS}/<category>.root"
echo " Categories       : ${CATS_TO_PROCESS[*]}"
echo " Parallel Jobs    : ${N_JOBS}"
echo "======================================================================"

merge_single_run() {
    local cat="$1"
    local run_dir="$2"
    local run_name=$(basename "${run_dir}")
    local out_run_file="${OUT_RUNS}/${run_name}.root"

    local part_files=($(find "${run_dir}" -name "part_*.root" 2>/dev/null | sort))
    if [ ${#part_files[@]} -eq 0 ]; then
        return 0
    fi

    if [ "${FORCE}" -eq 0 ] && [ -f "${out_run_file}" ]; then
        local out_size=$(stat -c%s "${out_run_file}" 2>/dev/null || echo 0)
        if [ "${out_size}" -gt 1000 ]; then
            echo " ~ [SKIP] ${out_run_file} already exists (${out_size} bytes)."
            return 0
        fi
    fi

    echo " ~ [MERGE RUN] ${cat}/${run_name} (${#part_files[@]} partitions) -> ${out_run_file}"
    local tmp_run="${out_run_file}.tmp.$$"
    hadd -f -k "${tmp_run}" "${part_files[@]}" >/dev/null 2>&1
    mv -f "${tmp_run}" "${out_run_file}"
}

export -f merge_single_run
export OUT_RUNS FORCE

# 1. Merge each run into single run ROOT file
for cat in "${CATS_TO_PROCESS[@]}"; do
    cat_dir="${IN_BASE}/${cat}"
    if [ ! -d "${cat_dir}" ]; then
        continue
    fi

    echo "--- Step 1: Merging runs for ${cat} ---"
    if [ -n "${SPECIFIC_RUN}" ]; then
        rdir="${cat_dir}/run${SPECIFIC_RUN}"
        if [ -d "${rdir}" ]; then
            merge_single_run "${cat}" "${rdir}"
        fi
    else
        find "${cat_dir}" -mindepth 1 -maxdepth 1 -type d -name "run*" | sort | \
            xargs -P "${N_JOBS}" -I {} bash -c 'merge_single_run "'"${cat}"'" "{}"'
    fi
done

# 2. Merge all runs of the same category into category ROOT file
echo "--- Step 2: Merging categories into unified category ROOT files ---"
for cat in "${CATS_TO_PROCESS[@]}"; do
    cat_dir="${IN_BASE}/${cat}"
    if [ ! -d "${cat_dir}" ]; then
        continue
    fi

    cat_run_files=()
    for rdir in $(find "${cat_dir}" -mindepth 1 -maxdepth 1 -type d -name "run*" | sort); do
        rname=$(basename "${rdir}")
        rfile="${OUT_RUNS}/${rname}.root"
        if [ -f "${rfile}" ]; then
            cat_run_files+=("${rfile}")
        fi
    done

    out_cat_file="${OUT_CATS}/${cat}.root"
    if [ ${#cat_run_files[@]} -eq 0 ]; then
        echo " [WARNING] No merged run files found for ${cat} to combine into ${out_cat_file}."
        continue
    fi

    echo " ~ [MERGE CAT] ${cat} (${#cat_run_files[@]} runs) -> ${out_cat_file}"
    tmp_cat="${out_cat_file}.tmp.$$"
    hadd -f -k "${tmp_cat}" "${cat_run_files[@]}" >/dev/null 2>&1
    mv -f "${tmp_cat}" "${out_cat_file}"

    cat_size=$(stat -c%s "${out_cat_file}" 2>/dev/null || echo 0)
    echo "[SUCCESS] Generated ${out_cat_file} (${cat_size} bytes)."
done

echo "======================================================================"
echo "[FINISHED] All run and category merges complete."
echo "======================================================================"
