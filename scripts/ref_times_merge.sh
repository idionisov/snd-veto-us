#!/bin/bash
set -eo pipefail

# ==============================================================================
# ref_times_merge.sh: Merge reference time histograms across runs per category
#
# Usage:
#   ./ref_times_merge.sh [-c <catI|catII|all>] [-i <input.root>] [-o <output.root>]
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${SCRIPT_DIR}/../sndswEnv.sh" ]; then
    source "${SCRIPT_DIR}/../sndswEnv.sh"
elif [ -f "${SCRIPT_DIR}/sndswEnv.sh" ]; then
    source "${SCRIPT_DIR}/sndswEnv.sh"
fi

CATEGORY="all"
INPUT_FILE="/eos/user/i/idioniso/Timing/reference_times_2022.root"
OUTPUT_FILE="/eos/user/i/idioniso/Timing/reference_times_2022_merged.root"
IN_PLACE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--category|--cat)
            CATEGORY="$2"
            shift 2
            ;;
        -i|--input)
            INPUT_FILE="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        -u|--update|--in-place)
            IN_PLACE=1
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [-c <catI|catII|all>] [-i <input.root>] [-o <output.root>] [-u|--update]"
            echo ""
            echo "Options:"
            echo "  -c, --category <cat>   Target category: catI, catII, or all (default: all)"
            echo "  -i, --input <file>     Input ROOT file with run subdirectories (default: /eos/user/i/idioniso/Timing/reference_times_2022.root)"
            echo "  -o, --output <file>    Output ROOT file for merged histograms (default: /eos/user/i/idioniso/Timing/reference_times_2022_merged.root)"
            echo "  -u, --update           Also write unified histograms directly into the input ROOT file"
            exit 0
            ;;
        *)
            if [[ "$1" =~ ^(catI|catII|I|II|all)$ ]]; then
                CATEGORY="$1"
                shift
            else
                echo "Unknown option: $1" >&2
                exit 1
            fi
            ;;
    esac
done

if [ ! -f "${INPUT_FILE}" ]; then
    echo "[ERROR] Input file not found: ${INPUT_FILE}" >&2
    exit 1
fi

echo "======================================================================"
echo " SND@LHC Reference Time Histogram Merger"
echo " Input File   : ${INPUT_FILE}"
echo " Category     : ${CATEGORY}"
echo " Output File  : ${OUTPUT_FILE}"
echo " Update Input : $([ "${IN_PLACE}" -eq 1 ] && echo "Yes" || echo "No")"
echo "======================================================================"

python3 - << EOF
import os
import sys
import ROOT

ROOT.gROOT.SetBatch(True)

input_file = "${INPUT_FILE}"
output_file = "${OUTPUT_FILE}"
cat_arg = "${CATEGORY}".strip().lower()
in_place = (${IN_PLACE} == 1)

if cat_arg in ("i", "cati"):
    target_cats = ["catI"]
elif cat_arg in ("ii", "catii"):
    target_cats = ["catII"]
else:
    target_cats = ["catI", "catII"]

f_in = ROOT.TFile.Open(input_file, "READ")
if not f_in or f_in.IsZombie():
    print(f"[ERROR] Could not open {input_file}", file=sys.stderr)
    sys.exit(1)

merged_results = {}

for cat in target_cats:
    cat_dir = f_in.Get(cat)
    if not cat_dir:
        print(f"[WARNING] Directory '{cat}' not found in {input_file}.")
        continue

    u_ds = None
    u_sf = None
    runs_merged = 0

    keys = cat_dir.GetListOfKeys()
    for k in keys:
        r_dir = k.ReadObj()
        if not isinstance(r_dir, ROOT.TDirectoryFile):
            continue

        h_ds = r_dir.Get("reft-DS")
        h_sf = r_dir.Get("reft-SF")

        has_any = False
        if h_ds and h_ds.GetEntries() > 0:
            has_any = True
            if u_ds is None:
                u_ds = h_ds.Clone("reft-DS")
                u_ds.SetTitle(f"Unified DS Reference Time ({cat})")
                u_ds.SetDirectory(0)
            else:
                u_ds.Add(h_ds)

        if h_sf and h_sf.GetEntries() > 0:
            has_any = True
            if u_sf is None:
                u_sf = h_sf.Clone("reft-SF")
                u_sf.SetTitle(f"Unified SciFi Reference Time ({cat})")
                u_sf.SetDirectory(0)
            else:
                u_sf.Add(h_sf)

        if has_any:
            runs_merged += 1

    ds_entries = u_ds.GetEntries() if u_ds else 0
    sf_entries = u_sf.GetEntries() if u_sf else 0

    print(f"[MERGE] {cat}: Merged {runs_merged} runs -> reft-DS: {ds_entries:,.0f} entries, reft-SF: {sf_entries:,.0f} entries")
    merged_results[cat] = (u_ds, u_sf, runs_merged)

f_in.Close()

# 1. Write dedicated output ROOT file
os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
f_out = ROOT.TFile.Open(output_file, "RECREATE")
for cat, (u_ds, u_sf, n_runs) in merged_results.items():
    cdir = f_out.mkdir(cat)
    cdir.cd()
    if u_ds:
        u_ds.Write("reft-DS", ROOT.TObject.kOverwrite)
    if u_sf:
        u_sf.Write("reft-SF", ROOT.TObject.kOverwrite)
f_out.Close()
print(f"[SUCCESS] Saved unified histograms to: {output_file}")

# 2. Optionally update input file directly
if in_place:
    f_up = ROOT.TFile.Open(input_file, "UPDATE")
    for cat, (u_ds, u_sf, n_runs) in merged_results.items():
        cdir = f_up.GetDirectory(cat)
        if not cdir:
            cdir = f_up.mkdir(cat)
        cdir.cd()
        if u_ds:
            u_ds.Write("reft-DS-unified", ROOT.TObject.kOverwrite)
        if u_sf:
            u_sf.Write("reft-SF-unified", ROOT.TObject.kOverwrite)
    f_up.Close()
    print(f"[SUCCESS] Updated {input_file} with unified histograms (reft-DS-unified, reft-SF-unified).")

EOF

echo "======================================================================"
echo "[COMPLETE] Unified reference time histograms generated successfully."
echo "======================================================================"
