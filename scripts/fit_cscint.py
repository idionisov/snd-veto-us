#!/usr/bin/env python3
"""
fit_cscint.py
-------------
Extracts the effective scintillator speed c_scint, its statistical fit error,
and its systematic error for each SiPM channel from merged cscint ROOT files.

Usage:
  ./fit_cscint.py -i /eos/user/i/idioniso/Timing/cscint/runs/run4427.root -o run4427_cscint.json
  ./fit_cscint.py --input-dir /eos/user/i/idioniso/Timing/cscint/runs -o /eos/user/i/idioniso/Timing/cscint/fits
"""

import os
import sys
import glob
import json
import argparse
import numpy as np

try:
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError
except ImportError:
    print("[ERROR] PyROOT is required to execute fit_cscint.py")
    sys.exit(1)


def fit_single_2d_hist(h2, ref="DS", sipm=0, fit_min=-55.0, fit_max=-5.0, min_slice_entries=15):
    """
    Fits c_scint for a single 2D histogram h2 (x_pred vs dt).
    """
    if h2 is None or h2.GetEntries() < 100:
        return None

    side_sign = 1.0 if sipm < 8 else -1.0
    gr = ROOT.TGraphErrors()

    ip = 0
    py_slice = ROOT.TH1D()
    for bx in range(1, h2.GetNbinsX() + 1):
        x = h2.GetXaxis().GetBinCenter(bx)
        if x < fit_min or x > fit_max:
            continue
        py = h2.ProjectionY("h_py_temp", bx, bx)
        if py.GetEntries() < min_slice_entries:
            continue

        max_bin = py.GetMaximumBin()
        mode = py.GetBinCenter(max_bin)
        rms = py.GetRMS()
        fit_range = max(0.8, min(1.8, 1.5 * rms))

        fg = ROOT.TF1("fg_temp", "gaus", mode - fit_range, mode + fit_range)
        fg.SetParameters(py.GetBinContent(max_bin), mode, max(0.3, rms))
        res_g = py.Fit(fg, "QNS0")

        mpv = None
        mpv_err = None
        if int(res_g) == 0 and 0 < fg.GetParError(1) < 2.5:
            p1 = fg.GetParameter(1)
            if mode - 2.5 < p1 < mode + 2.5:
                mpv = p1
                mpv_err = fg.GetParError(1)

        if mpv is None:
            mpv = mode
            mpv_err = py.GetBinWidth(max_bin) / (12.0 ** 0.5)

        gr.SetPoint(ip, x, mpv)
        gr.SetPointError(ip, 0.0, mpv_err)
        ip += 1

    if gr.GetN() < 5:
        return None

    func = ROOT.TF1("fit_pol1_temp", "pol1", fit_min, fit_max)
    gr.Fit(func, "QNS0R")

    slope = func.GetParameter(1)
    slope_err = func.GetParError(1)
    const = func.GetParameter(0)
    const_err = func.GetParError(0)
    chi2 = func.GetChisquare()
    ndf = max(1, func.GetNDF())

    if abs(slope) < 1e-7 or slope_err <= 0:
        return None

    c_scint = side_sign / slope
    delta_c_fit = abs(slope_err / (slope ** 2))

    if c_scint <= 0 or c_scint > 50.0:
        return None

    # Systematic error: 5 disjoint sub-segment fits (same as TimeWalk.py)
    n_segments = 5
    total_span = fit_max - fit_min
    seg_width = total_span / n_segments

    subrange_fits = []
    for s_idx in range(n_segments):
        x_low = fit_min + s_idx * seg_width
        x_high = fit_min + (s_idx + 1) * seg_width
        n_pts = sum(1 for i in range(gr.GetN()) if x_low <= gr.GetPointX(i) <= x_high)
        if n_pts < 3:
            continue
        seg_func = ROOT.TF1(f"seg_temp_{s_idx}", "pol1", x_low, x_high)
        gr.Fit(seg_func, "QNS0R")
        m_s = seg_func.GetParameter(1)
        m_s_err = seg_func.GetParError(1)
        if abs(m_s) > 1e-7 and m_s_err > 0:
            c_s = side_sign / m_s
            c_s_err = abs(m_s_err / (m_s ** 2))
            if 5.0 < c_s < 40.0:
                subrange_fits.append([float(c_s), float(c_s_err)])

    if len(subrange_fits) >= 2:
        segments_arr = np.array(subrange_fits, dtype=float)
        c_vals = segments_arr[:, 0]
        sig_vals = segments_arr[:, 1]
        w_vals = 1.0 / (sig_vals ** 2)
        c_mu_pdg = float(np.sum(w_vals * c_vals) / np.sum(w_vals))
        sigma_0 = float(1.0 / np.sqrt(np.sum(w_vals)))
        chi2_sub = float(np.sum(w_vals * (c_vals - c_mu_pdg) ** 2))
        ndf_sub = max(1, len(c_vals) - 1)
        chi2_red_sub = chi2_sub / ndf_sub
        s_scale = float(np.sqrt(chi2_red_sub)) if chi2_red_sub > 1.0 else 1.0
        sigma_final = s_scale * sigma_0
        delta_c_syst = float(np.sqrt(max(0.0, sigma_final ** 2 - sigma_0 ** 2)))
    else:
        delta_c_syst = float(delta_c_fit)

    delta_c_tot = float(np.sqrt(delta_c_fit ** 2 + delta_c_syst ** 2))

    return {
        "c_scint": float(c_scint),
        "delta_c_fit": float(delta_c_fit),
        "delta_c_syst": float(delta_c_syst),
        "delta_c_tot": delta_c_tot,
        "slope": float(slope),
        "slope_err": float(slope_err),
        "intercept": float(const),
        "intercept_err": float(const_err),
        "chi2": float(chi2),
        "ndf": int(ndf),
        "chi2_ndf": float(chi2 / ndf),
        "n_points": int(gr.GetN()),
    }


def fit_file(root_path: str, verbose: bool = False):
    """
    Fits c_scint for all SiPM channels in root_path.
    Returns:
      {
        "DS": { "<detID_sipm>": { "sipm": <int>, "c_scint": ..., "delta_c_fit": ..., "delta_c_syst": ..., "delta_c_tot": ... } },
        "SF": { ... },
        "summary": { "DS": { "mean": ..., "std": ... }, "SF": { ... } }
      }
    """
    f = ROOT.TFile.Open(root_path, "READ")
    if not f or f.IsZombie():
        print(f"[ERROR] Cannot open ROOT file: {root_path}", file=sys.stderr)
        return None

    results = {"DS": {}, "SF": {}}

    key_names = [k.GetName() for k in f.GetListOfKeys()]
    total_ch = len(key_names)

    for idx, k in enumerate(key_names):
        parts = k.split("_")
        if len(parts) != 2:
            continue
        try:
            detID = int(parts[0])
            sipm = int(parts[1])
        except ValueError:
            continue

        if k == "21005_15":
            continue

        # Fit DS
        h2_ds = f.Get(f"{k}/dt-DS")
        if h2_ds and h2_ds.InheritsFrom("TH2"):
            res_ds = fit_single_2d_hist(h2_ds, ref="DS", sipm=sipm, fit_min=-55.0, fit_max=-5.0, min_slice_entries=15)
            if res_ds is not None:
                res_ds["sipm"] = sipm
                res_ds["detID"] = detID
                results["DS"][k] = res_ds

        # Fit SF
        h2_sf = f.Get(f"{k}/dt-SF")
        if h2_sf and h2_sf.InheritsFrom("TH2"):
            res_sf = fit_single_2d_hist(h2_sf, ref="SF", sipm=sipm, fit_min=-44.0, fit_max=-8.0, min_slice_entries=15)
            if res_sf is not None:
                res_sf["sipm"] = sipm
                res_sf["detID"] = detID
                results["SF"][k] = res_sf

        if verbose and (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{total_ch} channels...", flush=True)

    f.Close()

    # Calculate summary statistics
    summary = {}
    for ref in ("DS", "SF"):
        c_vals = [d["c_scint"] for d in results[ref].values()]
        c_errs = [d["delta_c_tot"] for d in results[ref].values()]
        if c_vals:
            weights = 1.0 / (np.array(c_errs) ** 2)
            w_mean = float(np.sum(weights * np.array(c_vals)) / np.sum(weights))
            w_sem = float(1.0 / np.sqrt(np.sum(weights)))
            summary[ref] = {
                "n_channels": len(c_vals),
                "mean": float(np.mean(c_vals)),
                "std": float(np.std(c_vals)),
                "weighted_mean": w_mean,
                "weighted_sem": w_sem,
            }
        else:
            summary[ref] = {"n_channels": 0, "mean": None, "std": None, "weighted_mean": None, "weighted_sem": None}

    results["summary"] = summary
    return results


def main():
    parser = argparse.ArgumentParser(description="Extract c_scint via linear fitting on cscint ROOT files.")
    parser.add_argument("-i", "--input", type=str, help="Single input merged ROOT file")
    parser.add_argument("-o", "--output", type=str, help="Output JSON file or directory")
    parser.add_argument("--input-dir", type=str, help="Directory containing merged run ROOT files")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print progress")
    args = parser.parse_args()

    if args.input:
        out_json = args.output if args.output else args.input.replace(".root", "_cscint.json")
        res = fit_file(args.input, verbose=args.verbose)
        if res is not None:
            os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
            with open(out_json, "w") as jf:
                json.dump(res, jf, indent=2)
            ds_sum = res["summary"]["DS"]
            print(f"[SUCCESS] Saved fit results to {out_json}")
            if ds_sum["n_channels"] > 0:
                print(f"  -> DS: {ds_sum['n_channels']} channels, c_scint = {ds_sum['weighted_mean']:.2f} +/- {ds_sum['weighted_sem']:.2f} cm/ns (mean={ds_sum['mean']:.2f})")

    elif args.input_dir:
        out_dir = args.output if args.output else os.path.join(args.input_dir, "fits")
        os.makedirs(out_dir, exist_ok=True)
        files = sorted(glob.glob(os.path.join(args.input_dir, "run*.root")))
        print(f"Processing {len(files)} run files in {args.input_dir}...")

        all_runs_summary = []
        for fpath in files:
            bname = os.path.basename(fpath)
            rnum_str = bname.replace(".root", "").replace("run", "")
            try:
                rnum = int(rnum_str)
            except ValueError:
                continue

            res = fit_file(fpath, verbose=args.verbose)
            if res is None:
                continue

            out_run_json = os.path.join(out_dir, f"{bname.replace('.root', '')}_cscint.json")
            with open(out_run_json, "w") as jf:
                json.dump(res, jf, indent=2)

            all_runs_summary.append({
                "run": rnum,
                "summary": res["summary"],
                "file": out_run_json
            })
            print(f"  -> Run {rnum}: DS N={res['summary']['DS']['n_channels']}, SF N={res['summary']['SF']['n_channels']}")

        master_json = os.path.join(out_dir, "all_runs_cscint_summary.json")
        all_runs_summary.sort(key=lambda d: d["run"])
        with open(master_json, "w") as jf:
            json.dump(all_runs_summary, jf, indent=2)
        print(f"[SUCCESS] Consolidated summary for {len(all_runs_summary)} runs saved to {master_json}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
