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

    x_pts = np.array([gr.GetPointX(i) for i in range(gr.GetN())], dtype=float)
    y_pts = np.array([gr.GetPointY(i) for i in range(gr.GetN())], dtype=float)
    ey_pts = np.array([gr.GetErrorY(i) for i in range(gr.GetN())], dtype=float)

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
        "x_arr": x_pts,
        "y_arr": y_pts,
        "ey_arr": ey_pts,
    }


def build_cscint_canvas(h2, fixed_ch: str, ref: str, fit_res: dict, fit_min: float, fit_max: float):
    """
    Constructs a 2-pad canvas containing:
      Top pad: 2D histogram + slice data points (stat error) + total uncertainty band + linear fit line.
      Bottom pad: Fit / Data with separable statistical and systematic error bars adding up to total uncertainty.
    """
    ROOT.TH1.AddDirectory(False)
    cname = f"c_cscint_{ref}_{fixed_ch}"
    c = ROOT.TCanvas(cname, f"c_scint Fit - Channel {fixed_ch} ({ref} Reference)", 950, 800)

    pad1 = ROOT.TPad(f"pad1_{ref}_{fixed_ch}", "Upper Pad", 0.0, 0.28, 1.0, 1.0)
    pad2 = ROOT.TPad(f"pad2_{ref}_{fixed_ch}", "Lower Pad", 0.0, 0.0, 1.0, 0.28)
    ROOT.SetOwnership(pad1, False)
    ROOT.SetOwnership(pad2, False)

    pad1.SetBottomMargin(0.02)
    pad1.SetLeftMargin(0.12)
    pad1.SetRightMargin(0.12)
    pad1.SetGrid()

    pad2.SetTopMargin(0.03)
    pad2.SetBottomMargin(0.32)
    pad2.SetLeftMargin(0.12)
    pad2.SetRightMargin(0.12)
    pad2.SetGrid()

    pad1.Draw()
    pad2.Draw()

    x_arr = fit_res["x_arr"]
    y_arr = fit_res["y_arr"]
    ey_arr = fit_res["ey_arr"]
    n_pts = len(x_arr)

    c_scint = fit_res["c_scint"]
    delta_c_fit = fit_res["delta_c_fit"]
    delta_c_syst = fit_res["delta_c_syst"]
    slope = fit_res["slope"]
    intercept = fit_res["intercept"]
    chi2 = fit_res["chi2"]
    ndf = fit_res["ndf"]

    # Calculate point-by-point systematic uncertainty and total uncertainty
    sigma_m_syst = abs(delta_c_syst / (c_scint ** 2)) if c_scint > 0 else 0.0
    x_mean = np.mean(x_arr) if n_pts > 0 else 0.0
    w_sum = np.sum(1.0 / (ey_arr ** 2)) if n_pts > 0 else 1.0
    sigma_floor = np.sqrt(max(0.0, (chi2 - ndf) / w_sum)) if ndf > 0 else 0.0
    sigma_syst_arr = np.sqrt((sigma_m_syst * (x_arr - x_mean)) ** 2 + sigma_floor ** 2)
    ey_tot = np.sqrt(ey_arr ** 2 + sigma_syst_arr ** 2)

    dx_band = np.full(n_pts, 0.5)
    x_range_min = fit_min - 3.0
    x_range_max = fit_max + 3.0

    # Top Pad: 2D distribution + Slice Data + Fit
    pad1.cd()
    ROOT.gStyle.SetPalette(ROOT.kRainBow)
    h2_clone = h2.Clone(f"h2_{ref}_{fixed_ch}_clone")
    ROOT.SetOwnership(h2_clone, False)
    h2_clone.SetDirectory(0)
    h2_clone.SetTitle("")
    h2_clone.GetXaxis().SetLabelSize(0)
    h2_clone.GetXaxis().SetTitle("")
    h2_clone.GetYaxis().SetTitle(f"t_{{0}}^{{{ref}}} - t_{{SiPM}} [ns]")
    h2_clone.GetYaxis().SetTitleSize(0.048)
    h2_clone.GetYaxis().SetTitleOffset(1.10)
    h2_clone.GetYaxis().SetLabelSize(0.042)
    h2_clone.GetXaxis().SetRangeUser(x_range_min, x_range_max)
    h2_clone.Draw("COLZ")

    g_data_tot = ROOT.TGraphErrors(n_pts, x_arr, y_arr, dx_band, ey_tot)
    g_data_tot.SetName(f"g_data_total_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_data_tot, False)
    g_data_tot.SetFillColor(ROOT.kBlue + 2)
    g_data_tot.SetFillStyle(3004)
    g_data_tot.SetLineColor(ROOT.kBlue + 2)
    g_data_tot.Draw("E2 SAME")

    g_data_stat = ROOT.TGraphErrors(n_pts, x_arr, y_arr, np.zeros(n_pts), ey_arr)
    g_data_stat.SetName(f"g_data_stat_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_data_stat, False)
    g_data_stat.SetMarkerStyle(20)
    g_data_stat.SetMarkerSize(0.6)
    g_data_stat.SetMarkerColor(ROOT.kBlack)
    g_data_stat.SetLineColor(ROOT.kBlack)
    g_data_stat.Draw("PE SAME")

    fit_func = ROOT.TF1(f"func_{ref}_{fixed_ch}", "pol1", fit_min, fit_max)
    fit_func.SetParameters(intercept, slope)
    ROOT.SetOwnership(fit_func, False)
    fit_func.SetLineColor(ROOT.kRed + 1)
    fit_func.SetLineWidth(2)
    fit_func.Draw("SAME")

    leg = ROOT.TLegend(0.15, 0.68, 0.65, 0.90)
    leg.SetBorderSize(1)
    leg.SetFillColorAlpha(ROOT.kWhite, 0.88)
    leg.SetTextFont(42)
    leg.SetTextSize(0.030)
    leg.SetHeader(f"Channel {fixed_ch} ({ref} Reference)", "C")
    leg.AddEntry(g_data_stat, "Data (Stat. error #sigma_{fit})", "lep")
    leg.AddEntry(g_data_tot, "Total Uncertainty (#sigma_{fit} #oplus #sigma_{syst})", "f")
    leg.AddEntry(fit_func, f"Fit: c_{{scint}} = {c_scint:.2f} #pm {delta_c_fit:.2f} (fit) #pm {delta_c_syst:.2f} (syst) cm/ns", "l")
    leg.AddEntry("", f"#chi^{{2}}/ndf = {chi2:.1f}/{ndf} ({chi2/ndf:.2f}), c_{{scint}}^{{tot}} = {c_scint:.2f} #pm {fit_res['delta_c_tot']:.2f} cm/ns", "")
    ROOT.SetOwnership(leg, False)
    leg.Draw()

    # Bottom Pad: Fit / Data
    pad2.cd()
    y_fit_pts = slope * x_arr + intercept
    ratio = y_fit_pts / y_arr
    eratio_stat = np.abs(ratio / y_arr) * ey_arr
    eratio_tot = np.abs(ratio / y_arr) * ey_tot

    g_ratio_tot = ROOT.TGraphErrors(n_pts, x_arr, ratio, dx_band, eratio_tot)
    g_ratio_tot.SetName(f"g_ratio_total_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_tot, False)
    g_ratio_tot.SetTitle(";x_{predicted} [cm];Fit / Data")
    g_ratio_tot.SetFillColor(ROOT.kBlue + 2)
    g_ratio_tot.SetFillStyle(3004)
    g_ratio_tot.SetLineColor(ROOT.kBlue + 2)
    g_ratio_tot.GetXaxis().SetRangeUser(x_range_min, x_range_max)
    g_ratio_tot.GetYaxis().SetRangeUser(0.85, 1.15)
    g_ratio_tot.GetXaxis().SetTitleSize(0.12)
    g_ratio_tot.GetXaxis().SetLabelSize(0.09)
    g_ratio_tot.GetXaxis().SetTitleOffset(0.95)
    g_ratio_tot.GetYaxis().SetTitleSize(0.11)
    g_ratio_tot.GetYaxis().SetLabelSize(0.08)
    g_ratio_tot.GetYaxis().SetTitleOffset(0.48)
    g_ratio_tot.GetYaxis().SetNdivisions(505)
    g_ratio_tot.Draw("AE2")

    g_ratio_stat = ROOT.TGraphErrors(n_pts, x_arr, ratio, np.zeros(n_pts), eratio_stat)
    g_ratio_stat.SetName(f"g_ratio_stat_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_stat, False)
    g_ratio_stat.SetMarkerStyle(20)
    g_ratio_stat.SetMarkerSize(0.5)
    g_ratio_stat.SetMarkerColor(ROOT.kBlack)
    g_ratio_stat.SetLineColor(ROOT.kBlack)
    g_ratio_stat.Draw("PE SAME")

    line1 = ROOT.TLine(x_range_min, 1.0, x_range_max, 1.0)
    ROOT.SetOwnership(line1, False)
    line1.SetLineColor(ROOT.kRed + 1)
    line1.SetLineStyle(2)
    line1.SetLineWidth(2)
    line1.Draw("SAME")

    c.Update()
    return c


def fit_file(root_path: str, save_canvas: bool = True, verbose: bool = False):
    """
    Fits c_scint for all SiPM channels in root_path.
    If save_canvas=True, opens root_path in UPDATE mode and stores a 2-pad fit canvas
    into each channel directory.
    Returns:
      {
        "DS": { "<detID_sipm>": { "sipm": <int>, "c_scint": ..., "delta_c_fit": ..., "delta_c_syst": ..., "delta_c_tot": ... } },
        "SF": { ... },
        "summary": { "DS": { "mean": ..., "std": ... }, "SF": { ... } }
      }
    """
    mode = "UPDATE" if save_canvas else "READ"
    f = ROOT.TFile.Open(root_path, mode)
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
                if save_canvas:
                    canv_ds = build_cscint_canvas(h2_ds, k, "DS", res_ds, fit_min=-55.0, fit_max=-5.0)
                    ch_dir = f.GetDirectory(k)
                    if not ch_dir:
                        ch_dir = f.mkdir(k)
                    ch_dir.WriteObject(canv_ds, canv_ds.GetName(), "kOverwrite")
                    canv_ds.Close()
                    del canv_ds

                for arr_k in ("x_arr", "y_arr", "ey_arr"):
                    res_ds.pop(arr_k, None)
                res_ds["sipm"] = sipm
                res_ds["detID"] = detID
                results["DS"][k] = res_ds

        # Fit SF
        h2_sf = f.Get(f"{k}/dt-SF")
        if h2_sf and h2_sf.InheritsFrom("TH2"):
            res_sf = fit_single_2d_hist(h2_sf, ref="SF", sipm=sipm, fit_min=-44.0, fit_max=-8.0, min_slice_entries=15)
            if res_sf is not None:
                if save_canvas:
                    canv_sf = build_cscint_canvas(h2_sf, k, "SF", res_sf, fit_min=-44.0, fit_max=-8.0)
                    ch_dir = f.GetDirectory(k)
                    if not ch_dir:
                        ch_dir = f.mkdir(k)
                    ch_dir.WriteObject(canv_sf, canv_sf.GetName(), "kOverwrite")
                    canv_sf.Close()
                    del canv_sf

                for arr_k in ("x_arr", "y_arr", "ey_arr"):
                    res_sf.pop(arr_k, None)
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
    parser.add_argument("--no-canvas", dest="save_canvas", action="store_false", default=True,
                        help="Do not store fit canvases in the input ROOT file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print progress")
    args = parser.parse_args()

    if args.input:
        out_json = args.output if args.output else args.input.replace(".root", "_cscint.json")
        res = fit_file(args.input, save_canvas=args.save_canvas, verbose=args.verbose)
        if res is not None:
            os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
            with open(out_json, "w") as jf:
                json.dump(res, jf, indent=2)
            ds_sum = res["summary"]["DS"]
            print(f"[SUCCESS] Saved fit results to {out_json}")
            if ds_sum["n_channels"] > 0:
                print(f"  -> DS: {ds_sum['n_channels']} channels, c_scint = {ds_sum['weighted_mean']:.2f} +/- {ds_sum['weighted_sem']:.2f} cm/ns (mean={ds_sum['mean']:.2f})")
            if args.save_canvas:
                print(f"[SUCCESS] Saved fit canvases into input ROOT file {args.input}")

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

            res = fit_file(fpath, save_canvas=args.save_canvas, verbose=args.verbose)
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
