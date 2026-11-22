#!/bin/bash
set -eo pipefail

YEAR="${1:-all}"
RUNS_DIR="/eos/user/i/idioniso/Timing/cscint/runs"
CATS_DIR="/eos/user/i/idioniso/Timing/cscint/categories"
mkdir -p "${CATS_DIR}"

if [ -f "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh" ]; then
    source "/afs/cern.ch/work/i/idioniso/snd-veto-us/sndswEnv.sh"
fi

declare -A RUNS_BY_YEAR
RUNS_BY_YEAR[2023]="6079 6568 6574 6577 6590 6593 6596 6640 6663 6667"
RUNS_BY_YEAR[2024]="8638 8724 9094 9269 9361 9436 9622 9649 9685 9880"
RUNS_BY_YEAR[2025]="11124 11193 11241 11555 11720 11744 11747 12205 12213 12217"
RUNS_BY_YEAR[2026]="13085 13098 13101 13104 13162 13406 13480 13503 13508 13520"

merge_year() {
    local y="$1"
    local run_list=(${RUNS_BY_YEAR[$y]})
    local target="${CATS_DIR}/catIII_${y}.root"
    local files=()

    echo "======================================================================"
    echo " Merging Category III Year ${y} (${#run_list[@]} runs)"
    echo " Destination: ${target}"
    echo "======================================================================"

    for r in "${run_list[@]}"; do
        rf="${RUNS_DIR}/run${r}.root"
        if [ -f "${rf}" ]; then
            files+=("${rf}")
        else
            echo " [WARNING] Missing run file: ${rf}"
        fi
    done

    if [ ${#files[@]} -eq 0 ]; then
        echo " [ERROR] No run files found for Year ${y}!" >&2
        return 1
    fi

    echo " Found ${#files[@]} / ${#run_list[@]} run files to merge."
    local scratch="${_CONDOR_SCRATCH_DIR:-/tmp}/merge_catIII_${y}_$$"
    mkdir -p "${scratch}"
    local tmp_target="${scratch}/catIII_${y}.root"

    hadd -f -k -j 4 "${tmp_target}" "${files[@]}"

    cp -f "${tmp_target}" "${target}.tmp"
    mv -f "${target}.tmp" "${target}"
    rm -rf "${scratch}"

    local final_size
    final_size=$(stat -c%s "${target}" 2>/dev/null || echo 0)
    echo "[SUCCESS] Generated ${target} (${final_size} bytes)"
}

if [[ "${YEAR}" =~ ^(2023|2024|2025|2026)$ ]]; then
    merge_year "${YEAR}"
elif [ "${YEAR}" = "all" ]; then
    for y in 2023 2024 2025 2026; do
        merge_year "${y}"
    done
else
    echo "Usage: $0 [2023|2024|2025|2026|all]" >&2
    exit 1
fi
