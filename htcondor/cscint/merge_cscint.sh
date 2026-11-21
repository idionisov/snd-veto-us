#!/bin/bash
set -eo pipefail

# ==============================================================================
# Merge Partition Histograms for cscint (SiPM Ref Diff):
#   1. Merges all partition histograms of each run into a single run ROOT file
#      with all histograms added:
#        <out_dir>/runs/run<RUN>.root
#   2. Merges all runs of each category/year into unified category ROOT files:
#        <out_dir>/categories/<target>.root
#      Supported targets: catI, catII, catIII_2023, catIII_2024, catIII_2025, catIII_2026
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
    echo "  -c, --category <cat>  Category to merge (catI, catII, catIII_2023, catIII_2024,"
    echo "                        catIII_2025, catIII_2026, catIII, or all; default: all)"
    echo "                        Accepts comma-separated list, e.g. -c catII,catIII_2023"
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

# Resolve target categories/years
ALL_CAT3_TARGETS=("catIII_2023" "catIII_2024" "catIII_2025" "catIII_2026")
TARGETS_TO_PROCESS=()

IFS=',' read -ra INPUT_CATS <<< "${CATEGORY}"
for cat_item in "${INPUT_CATS[@]}"; do
    cat_item="${cat_item// /}" # trim whitespace
    case "${cat_item}" in
        all)
            TARGETS_TO_PROCESS+=("catI" "catII" "${ALL_CAT3_TARGETS[@]}")
            ;;
        catIII)
            TARGETS_TO_PROCESS+=("${ALL_CAT3_TARGETS[@]}")
            ;;
        catI|catII|catIII_2023|catIII_2024|catIII_2025|catIII_2026)
            TARGETS_TO_PROCESS+=("${cat_item}")
            ;;
        *)
            echo "[ERROR] Unknown category or year: ${cat_item}" >&2
            usage
            ;;
    esac
done

# Remove duplicates while preserving order
read -r -a TARGETS_TO_PROCESS <<< "$(echo "${TARGETS_TO_PROCESS[@]}" | tr ' ' '\n' | awk '!seen[$0]++' | tr '\n' ' ')"

echo "======================================================================"
echo " SND@LHC cscint (SiPM Ref Diff) Histogram Merger"
echo " Input Partitions : ${IN_BASE}"
echo " Output Runs      : ${OUT_RUNS}/run<RUN>.root"
echo " Output Categories: ${OUT_CATS}/<target>.root"
echo " Targets          : ${TARGETS_TO_PROCESS[*]}"
if [ -n "${SPECIFIC_RUN}" ]; then
    echo " Target Run       : ${SPECIFIC_RUN}"
fi
echo " Parallel Jobs    : ${N_JOBS}"
echo " Force Overwrite  : ${FORCE}"
echo "======================================================================"

get_cat_dir() {
    local target="$1"
    case "$target" in
        catI) echo "${IN_BASE}/catI" ;;
        catII) echo "${IN_BASE}/catII" ;;
        catIII*) echo "${IN_BASE}/catIII" ;;
        *) echo "" ;;
    esac
}

get_runs_for_target() {
    local target="$1"
    local cat_dir
    cat_dir="$(get_cat_dir "$target")"
    if [ ! -d "${cat_dir}" ]; then
        return 0
    fi

    for rdir in $(find "${cat_dir}" -mindepth 1 -maxdepth 1 -type d -name "run*" | sort -V); do
        local rname=$(basename "${rdir}")
        local rnum="${rname#run}"
        if ! [[ "${rnum}" =~ ^[0-9]+$ ]]; then
            continue
        fi
        case "$target" in
            catI|catII)
                echo "${rdir}"
                ;;
            catIII_2023)
                if [ "${rnum}" -ge 5483 ] && [ "${rnum}" -le 7500 ]; then
                    echo "${rdir}"
                fi
                ;;
            catIII_2024)
                if [ "${rnum}" -ge 7600 ] && [ "${rnum}" -le 10800 ]; then
                    echo "${rdir}"
                fi
                ;;
            catIII_2025)
                if [ "${rnum}" -ge 10900 ] && [ "${rnum}" -le 12790 ]; then
                    echo "${rdir}"
                fi
                ;;
            catIII_2026)
                if [ "${rnum}" -ge 12791 ]; then
                    echo "${rdir}"
                fi
                ;;
        esac
    done
}

merge_single_run() {
    local target="$1"
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

    echo " ~ [MERGE RUN] ${target}/${run_name} (${#part_files[@]} partitions) -> ${out_run_file}"
    local tmp_run="${TMPDIR:-/tmp}/${run_name}_$$.$RANDOM.root"
    hadd -f -k "${tmp_run}" "${part_files[@]}" >/dev/null 2>&1
    mv -f "${tmp_run}" "${out_run_file}"
}

export -f merge_single_run
export OUT_RUNS FORCE TMPDIR

# 1. Merge each run into single run ROOT file
for target in "${TARGETS_TO_PROCESS[@]}"; do
    cat_dir="$(get_cat_dir "${target}")"
    if [ ! -d "${cat_dir}" ]; then
        continue
    fi

    echo "--- Step 1: Merging runs for ${target} ---"
    if [ -n "${SPECIFIC_RUN}" ]; then
        rdir="${cat_dir}/run${SPECIFIC_RUN}"
        if [ -d "${rdir}" ]; then
            # Verify if specific run belongs to this target
            matching_runs=($(get_runs_for_target "${target}"))
            for mdir in "${matching_runs[@]}"; do
                if [ "${mdir}" = "${rdir}" ]; then
                    merge_single_run "${target}" "${rdir}"
                    break
                fi
            done
        fi
    else
        mapfile -t run_dirs < <(get_runs_for_target "${target}")
        if [ ${#run_dirs[@]} -eq 0 ]; then
            echo " ~ [SKIP] No partition runs found for ${target}."
            continue
        fi

        printf "%s\n" "${run_dirs[@]}" | \
            xargs -P "${N_JOBS}" -I {} bash -c 'merge_single_run "'"${target}"'" "{}"'
    fi
done

# 2. Merge all runs of each target into unified category ROOT file (skip if specific run was targeted)
if [ -z "${SPECIFIC_RUN}" ]; then
    echo "--- Step 2: Merging targets into unified category ROOT files ---"
    for target in "${TARGETS_TO_PROCESS[@]}"; do
        cat_dir="$(get_cat_dir "${target}")"
        if [ ! -d "${cat_dir}" ]; then
            continue
        fi

        mapfile -t target_run_dirs < <(get_runs_for_target "${target}")
        if [ ${#target_run_dirs[@]} -eq 0 ]; then
            continue
        fi

        target_run_files=()
        for rdir in "${target_run_dirs[@]}"; do
            rname=$(basename "${rdir}")
            rfile="${OUT_RUNS}/${rname}.root"
            if [ -f "${rfile}" ]; then
                target_run_files+=("${rfile}")
            fi
        done

        out_cat_file="${OUT_CATS}/${target}.root"
        if [ ${#target_run_files[@]} -eq 0 ]; then
            echo " [WARNING] No merged run files found for ${target} to combine into ${out_cat_file}."
            continue
        fi

        if [ "${FORCE}" -eq 0 ] && [ -f "${out_cat_file}" ]; then
            local out_size=$(stat -c%s "${out_cat_file}" 2>/dev/null || echo 0)
            if [ "${out_size}" -gt 1000 ]; then
                echo " ~ [SKIP] ${out_cat_file} already exists (${out_size} bytes)."
                continue
            fi
        fi

        echo " ~ [MERGE CAT] ${target} (${#target_run_files[@]} runs) -> ${out_cat_file}"
        tmp_cat="${TMPDIR:-/tmp}/${target}_$$.$RANDOM.root"
        hadd -f -k "${tmp_cat}" "${target_run_files[@]}" >/dev/null 2>&1
        mv -f "${tmp_cat}" "${out_cat_file}"

        cat_size=$(stat -c%s "${out_cat_file}" 2>/dev/null || echo 0)
        echo "[SUCCESS] Generated ${out_cat_file} (${cat_size} bytes)."
    done
fi

echo "======================================================================"
echo "[FINISHED] All run and category merges complete."
echo "======================================================================"
