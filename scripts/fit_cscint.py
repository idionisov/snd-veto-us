#!/usr/bin/env python3
"""
fit_cscint.py
-------------
Extracts the effective scintillator speed c_scint, its statistical fit error,
and its systematic error for each SiPM channel from merged cscint ROOT files.

Features:
  - Linear fit of dt vs x_pred with stat and systematic uncertainties.
  - Generates 2-pad canvases:
      Top pad: 2D histogram + fitted line + data points with stat & syst errors + legend
               with chi2/ndf, measured c_scint, stat and syst errors.
      Bottom pad: Data / Fit ratio with stat and syst errors drawn as hatched bands.
  - Sub-TDirectory for each SiPM containing slice projection histograms and Gaussian fits.
  - Run category filtering (catI, catII, catIII) and multi-processing support.

Usage:
  ./fit_cscint.py -i /eos/user/i/idioniso/Timing/cscint/runs/run5119.root -o run5119_cscint.json
  ./fit_cscint.py --input-dir /eos/user/i/idioniso/Timing/cscint/runs -c catII catIII -j 8
"""

import os
import sys
import glob
import json
import shutil
import tempfile
import argparse
import multiprocessing
import numpy as np

try:
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError
except ImportError:
    print("[ERROR] PyROOT is required to execute fit_cscint.py", file=sys.stderr)
    sys.exit(1)


def get_run_category(run_nr: int) -> str:
    """
    Determines category based on run number:
      - catI:   run <= 5116 or (5175 <= run <= 5192)
      - catII:  (5117 <= run <= 5174) or (5193 <= run <= 5412)
      - catIII: run >= 5413
    """
    if run_nr <= 5116 or (5175 <= run_nr <= 5192):
        return "catI"
    elif (5117 <= run_nr <= 5174) or (5193 <= run_nr <= 5412):
        return "catII"
    else:
        return "catIII"


def normalize_categories(cat_args):
    """Normalizes input categories into standard ['catI', 'catII', 'catIII']."""
    if not cat_args:
        return ["catII", "catIII"]
    if isinstance(cat_args, str):
        cat_args = [cat_args]

    cats = []
    for c in cat_args:
        for part in c.replace(",", " ").split():
            p = part.strip()
            if not p:
                continue
            p_lower = p.lower()
            if p_lower in ("cati", "i", "1"):
                cats.append("catI")
            elif p_lower in ("catii", "ii", "2"):
                cats.append("catII")
            elif p_lower in ("catiii", "iii", "3"):
                cats.append("catIII")
            elif p_lower == "all":
                return ["catI", "catII", "catIII"]
            else:
                cats.append(p)
    return list(dict.fromkeys(cats))


def fit_single_2d_hist(h2, ref="DS", sipm=0, ch_name="", fit_min=-55.0, fit_max=-5.0,
                       min_slice_entries=15, collect_slices=True):
    """
    Fits c_scint for a single 2D histogram h2 (x_pred vs dt).
    Also extracts vertical slice projection histograms and Gaussian fits.
    """
    if h2 is None or h2.GetEntries() < 100:
        return None

    side_sign = 1.0 if sipm < 8 else -1.0
    gr = ROOT.TGraphErrors()

    ip = 0
    slices_data = []

    fg = ROOT.TF1("fg_temp", "gaus", -10, 10, ROOT.TF1.EAddToList.kNo)

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

        fg.SetRange(mode - fit_range, mode + fit_range)
        fg.SetParameters(py.GetBinContent(max_bin), mode, max(0.3, rms))
        res_g = py.Fit(fg, "QNS0")

        mpv = None
        mpv_err = None
        fit_ok = False
        if int(res_g) == 0 and 0 < fg.GetParError(1) < 2.5:
            p1 = fg.GetParameter(1)
            if mode - 2.5 < p1 < mode + 2.5:
                mpv = p1
                mpv_err = fg.GetParError(1)
                fit_ok = True

        if mpv is None:
            mpv = mode
            mpv_err = py.GetBinWidth(max_bin) / (12.0 ** 0.5)

        gr.SetPoint(ip, x, mpv)
        gr.SetPointError(ip, 0.0, mpv_err)
        ip += 1

        if collect_slices:
            tag = ch_name if ch_name else str(sipm)
            py_clone = py.Clone(f"h_slice_{ref}_{tag}_bx{bx}")
            py_clone.SetDirectory(0)
            py_clone.SetTitle(f"Slice bx={bx} (x={x:.1f} cm);t_{{0}}^{{{ref}}} - t_{{SiPM}} [ns];Counts")
            fg_clone = ROOT.TF1(f"gaus_{ref}_{tag}_bx{bx}", "gaus", mode - fit_range, mode + fit_range, ROOT.TF1.EAddToList.kNo)
            fg_clone.SetParameters(fg.GetParameter(0), fg.GetParameter(1), fg.GetParameter(2))
            fg_clone.SetLineColor(ROOT.kRed + 1)
            fg_clone.SetLineWidth(2)
            ROOT.SetOwnership(fg_clone, False)
            py_clone.GetListOfFunctions().Add(fg_clone)
            slices_data.append(py_clone)

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
        "slices": slices_data,
    }


def build_cscint_canvas(h2, fixed_ch: str, ref: str, fit_res: dict, fit_min: float, fit_max: float):
    """
    Constructs a 2-pad canvas containing:
      Top pad: 2D histogram + slice data points (stat error) + total uncertainty band + linear fit line.
               Legend displaying chi2/ndf, c_scint, stat and syst errors.
      Bottom pad: Data / Fit ratio with stat and syst errors drawn as hatched areas.
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
    leg.AddEntry(fit_func, f"Fit: c_{{scint}} = {c_scint:.2f} #pm {delta_c_fit:.2f} (stat) #pm {delta_c_syst:.2f} (syst) cm/ns", "l")
    leg.AddEntry("", f"#chi^{{2}}/ndf = {chi2:.1f}/{ndf} ({chi2/ndf:.2f}), c_{{scint}}^{{tot}} = {c_scint:.2f} #pm {fit_res['delta_c_tot']:.2f} cm/ns", "")
    ROOT.SetOwnership(leg, False)
    leg.Draw()

    # Bottom Pad: Data / Fit
    pad2.cd()
    y_fit_pts = slope * x_arr + intercept
    denom = np.abs(y_fit_pts)
    denom[denom == 0] = 1e-6
    ratio = y_arr / y_fit_pts
    eratio_stat = ey_arr / denom
    eratio_syst = sigma_syst_arr / denom
    eratio_tot = ey_tot / denom

    g_ratio_tot = ROOT.TGraphErrors(n_pts, x_arr, ratio, dx_band, eratio_tot)
    g_ratio_tot.SetName(f"g_ratio_total_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_tot, False)
    g_ratio_tot.SetTitle(";x_{predicted} [cm];Data / Fit")
    g_ratio_tot.SetFillColor(ROOT.kBlue + 2)
    g_ratio_tot.SetFillStyle(3004)
    g_ratio_tot.SetLineColor(ROOT.kBlue + 2)
    g_ratio_tot.GetXaxis().SetRangeUser(x_range_min, x_range_max)
    r_min = max(0.6, float(np.min(ratio - eratio_tot) - 0.05))
    r_max = min(1.4, float(np.max(ratio + eratio_tot) + 0.05))
    g_ratio_tot.GetYaxis().SetRangeUser(min(0.85, r_min), max(1.15, r_max))
    g_ratio_tot.GetXaxis().SetTitleSize(0.12)
    g_ratio_tot.GetXaxis().SetLabelSize(0.09)
    g_ratio_tot.GetXaxis().SetTitleOffset(0.95)
    g_ratio_tot.GetYaxis().SetTitleSize(0.11)
    g_ratio_tot.GetYaxis().SetLabelSize(0.08)
    g_ratio_tot.GetYaxis().SetTitleOffset(0.48)
    g_ratio_tot.GetYaxis().SetNdivisions(505)
    g_ratio_tot.Draw("AE2")

    # Syst uncertainty hatched area
    g_ratio_syst = ROOT.TGraphErrors(n_pts, x_arr, ratio, dx_band, eratio_syst)
    g_ratio_syst.SetName(f"g_ratio_syst_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_syst, False)
    g_ratio_syst.SetFillColor(ROOT.kTeal - 5)
    g_ratio_syst.SetFillStyle(3005)
    g_ratio_syst.SetLineColor(ROOT.kTeal - 5)
    g_ratio_syst.Draw("E2 SAME")

    # Stat uncertainty hatched area
    g_ratio_stat_band = ROOT.TGraphErrors(n_pts, x_arr, ratio, dx_band, eratio_stat)
    g_ratio_stat_band.SetName(f"g_ratio_stat_band_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_stat_band, False)
    g_ratio_stat_band.SetFillColor(ROOT.kOrange + 7)
    g_ratio_stat_band.SetFillStyle(3004)
    g_ratio_stat_band.SetLineColor(ROOT.kOrange + 7)
    g_ratio_stat_band.Draw("E2 SAME")

    # Data points with stat error
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

    leg_ratio = ROOT.TLegend(0.14, 0.77, 0.88, 0.96)
    leg_ratio.SetNColumns(4)
    leg_ratio.SetBorderSize(0)
    leg_ratio.SetFillStyle(0)
    leg_ratio.SetTextFont(42)
    leg_ratio.SetTextSize(0.065)
    leg_ratio.AddEntry(g_ratio_stat, "Data / Fit", "lep")
    leg_ratio.AddEntry(g_ratio_stat_band, "Stat unc.", "f")
    leg_ratio.AddEntry(g_ratio_syst, "Syst unc.", "f")
    leg_ratio.AddEntry(g_ratio_tot, "Total unc.", "f")
    ROOT.SetOwnership(leg_ratio, False)
    leg_ratio.Draw()

    c.Update()
    return c


def fit_file(root_path: str, save_canvas: bool = True, save_slices: bool = True,
             save_slice_canvases: bool = False, output_path: str = None, verbose: bool = False):
    """
    Fits c_scint for all SiPM channels in root_path.
    If save_canvas=True, stores 2-pad fit canvas into each channel directory.
    If save_slices=True, stores vertical slice projection histograms and Gaussian fits
    in sub-TDirectories (gaussian_fits_DS and gaussian_fits_SF).
    """
    target_path = output_path if output_path else root_path

    # Use a local temporary file for atomic, high-performance I/O if on network fs
    is_network = root_path.startswith("/eos") or target_path.startswith("/eos")
    if is_network:
        tmp_fd, work_file = tempfile.mkstemp(suffix=".root", prefix="cscint_fit_")
        os.close(tmp_fd)
        shutil.copyfile(root_path, work_file)
    else:
        work_file = target_path
        if output_path and output_path != root_path:
            shutil.copyfile(root_path, work_file)

    mode = "UPDATE" if (save_canvas or save_slices) else "READ"
    f = ROOT.TFile.Open(work_file, mode)
    if not f or f.IsZombie():
        print(f"[ERROR] Cannot open ROOT file: {work_file}", file=sys.stderr)
        if is_network and os.path.exists(work_file):
            os.remove(work_file)
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

        ch_dir = f.GetDirectory(k)
        if not ch_dir:
            ch_dir = f.mkdir(k)

        # Fit DS
        h2_ds = f.Get(f"{k}/dt-DS")
        if h2_ds and h2_ds.InheritsFrom("TH2"):
            res_ds = fit_single_2d_hist(
                h2_ds, ref="DS", sipm=sipm, ch_name=k, fit_min=-55.0, fit_max=-5.0,
                min_slice_entries=15, collect_slices=save_slices
            )
            if res_ds is not None:
                if save_canvas:
                    canv_ds = build_cscint_canvas(h2_ds, k, "DS", res_ds, fit_min=-55.0, fit_max=-5.0)
                    ch_dir.WriteObject(canv_ds, canv_ds.GetName(), "kOverwrite")
                    ch_dir.WriteObject(canv_ds, "c_cscint_DS", "kOverwrite")
                    canv_ds.Close()
                    del canv_ds

                if save_slices and res_ds.get("slices"):
                    sub_ds = ch_dir.GetDirectory("gaussian_fits_DS")
                    if not sub_ds:
                        sub_ds = ch_dir.mkdir("gaussian_fits_DS")
                    sub_ds.cd()
                    for h_slice in res_ds["slices"]:
                        h_slice.Write(h_slice.GetName(), ROOT.TObject.kOverwrite)

                res_ds.pop("slices", None)
                for arr_k in ("x_arr", "y_arr", "ey_arr"):
                    res_ds.pop(arr_k, None)
                res_ds["sipm"] = sipm
                res_ds["detID"] = detID
                results["DS"][k] = res_ds

        # Fit SF
        h2_sf = f.Get(f"{k}/dt-SF")
        if h2_sf and h2_sf.InheritsFrom("TH2"):
            res_sf = fit_single_2d_hist(
                h2_sf, ref="SF", sipm=sipm, ch_name=k, fit_min=-44.0, fit_max=-8.0,
                min_slice_entries=15, collect_slices=save_slices
            )
            if res_sf is not None:
                if save_canvas:
                    canv_sf = build_cscint_canvas(h2_sf, k, "SF", res_sf, fit_min=-44.0, fit_max=-8.0)
                    ch_dir.WriteObject(canv_sf, canv_sf.GetName(), "kOverwrite")
                    ch_dir.WriteObject(canv_sf, "c_cscint_SF", "kOverwrite")
                    canv_sf.Close()
                    del canv_sf

                if save_slices and res_sf.get("slices"):
                    sub_sf = ch_dir.GetDirectory("gaussian_fits_SF")
                    if not sub_sf:
                        sub_sf = ch_dir.mkdir("gaussian_fits_SF")
                    sub_sf.cd()
                    for h_slice in res_sf["slices"]:
                        h_slice.Write(h_slice.GetName(), ROOT.TObject.kOverwrite)

                res_sf.pop("slices", None)
                for arr_k in ("x_arr", "y_arr", "ey_arr"):
                    res_sf.pop(arr_k, None)
                res_sf["sipm"] = sipm
                res_sf["detID"] = detID
                results["SF"][k] = res_sf

        if verbose and (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{total_ch} channels...", flush=True)

    f.Close()

    # If working on temporary file, atomically move it to target location
    if is_network:
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        shutil.move(work_file, target_path)

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


def _worker_process_run(task_args):
    """Worker task wrapper for multiprocessing."""
    fpath, rnum, cat, out_run_json, out_run_root, save_canvas, save_slices, save_slice_canvases, verbose = task_args
    try:
        res = fit_file(
            fpath,
            save_canvas=save_canvas,
            save_slices=save_slices,
            save_slice_canvases=save_slice_canvases,
            output_path=out_run_root,
            verbose=verbose
        )
        if res is None:
            return None

        os.makedirs(os.path.dirname(os.path.abspath(out_run_json)), exist_ok=True)
        with open(out_run_json, "w") as jf:
            json.dump(res, jf, indent=2)

        return {
            "run": rnum,
            "category": cat,
            "summary": res["summary"],
            "file": out_run_json,
            "root_file": out_run_root if out_run_root else fpath,
        }
    except Exception as exc:
        print(f"[ERROR] Failed processing run {rnum}: {exc}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Extract c_scint via linear fitting on cscint ROOT files.")
    parser.add_argument("-i", "--input", type=str, help="Single input merged ROOT file (run or category)")
    parser.add_argument("-o", "--output", type=str, help="Output JSON file or directory for results")
    parser.add_argument("--input-dir", type=str, help="Directory containing merged run ROOT files")
    parser.add_argument("-c", "--category", "--categories", nargs="+", default=["catII", "catIII"],
                        help="Categories to process when scanning input-dir: catII, catIII, or all (default: catII catIII)")
    parser.add_argument("-j", "--jobs", type=int, default=4,
                        help="Number of parallel worker processes (default: 4)")
    parser.add_argument("--save-slices", dest="save_slices", action="store_true", default=True,
                        help="Save Gaussian slice fits in sub-TDirectory (default: True)")
    parser.add_argument("--no-slices", dest="save_slices", action="store_false",
                        help="Do not save Gaussian slice fits")
    parser.add_argument("--save-slice-canvases", dest="save_slice_canvases", action="store_true", default=False,
                        help="Save individual TCanvas objects for slices (default: False; TH1D with attached TF1 is saved by default)")
    parser.add_argument("--no-slice-canvases", dest="save_slice_canvases", action="store_false",
                        help="Do not create TCanvas objects for slices (stores TH1D with attached TF1 only)")
    parser.add_argument("--no-canvas", dest="save_canvas", action="store_false", default=True,
                        help="Do not store fit canvases in the input ROOT file")
    parser.add_argument("--output-root-dir", type=str, default=None,
                        help="Optional output directory for modified ROOT files (default: update in-place)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print progress")
    args = parser.parse_args()

    if args.input:
        out_json = args.output if (args.output and args.output.endswith(".json")) else args.input.replace(".root", "_cscint.json")
        out_root = args.output_root_dir
        if out_root and os.path.isdir(out_root):
            out_root = os.path.join(out_root, os.path.basename(args.input))

        res = fit_file(
            args.input,
            save_canvas=args.save_canvas,
            save_slices=args.save_slices,
            save_slice_canvases=args.save_slice_canvases,
            output_path=out_root,
            verbose=args.verbose
        )
        if res is not None:
            os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
            with open(out_json, "w") as jf:
                json.dump(res, jf, indent=2)
            ds_sum = res["summary"]["DS"]
            print(f"[SUCCESS] Saved fit results to {out_json}")
            if ds_sum["n_channels"] > 0:
                print(f"  -> DS: {ds_sum['n_channels']} channels, c_scint = {ds_sum['weighted_mean']:.2f} +/- {ds_sum['weighted_sem']:.2f} cm/ns (mean={ds_sum['mean']:.2f})")
            if args.save_canvas:
                target_written = out_root if out_root else args.input
                print(f"[SUCCESS] Saved fit canvases and slice subdirectories into ROOT file: {target_written}")

    elif args.input_dir:
        target_cats = normalize_categories(args.category)
        out_dir = args.output if args.output else os.path.join(args.input_dir, "fits")
        os.makedirs(out_dir, exist_ok=True)

        all_files = sorted(glob.glob(os.path.join(args.input_dir, "run*.root")))
        tasks = []
        for fpath in all_files:
            bname = os.path.basename(fpath)
            rnum_str = bname.replace(".root", "").replace("run", "")
            try:
                rnum = int(rnum_str)
            except ValueError:
                continue

            cat = get_run_category(rnum)
            if cat not in target_cats:
                continue

            out_run_json = os.path.join(out_dir, f"{bname.replace('.root', '')}_cscint.json")
            out_run_root = None
            if args.output_root_dir:
                os.makedirs(args.output_root_dir, exist_ok=True)
                out_run_root = os.path.join(args.output_root_dir, bname)

            tasks.append((
                fpath, rnum, cat, out_run_json, out_run_root,
                args.save_canvas, args.save_slices, args.save_slice_canvases, args.verbose
            ))

        print(f"======================================================================")
        print(f" Processing {len(tasks)} runs matching categories {target_cats} (Parallel Jobs: {args.jobs})")
        print(f"======================================================================")

        all_runs_summary = []
        if args.jobs > 1 and len(tasks) > 1:
            with multiprocessing.Pool(processes=min(args.jobs, len(tasks))) as pool:
                for res_item in pool.imap_unordered(_worker_process_run, tasks):
                    if res_item is not None:
                        all_runs_summary.append(res_item)
                        rnum = res_item["run"]
                        ds_n = res_item["summary"]["DS"]["n_channels"]
                        sf_n = res_item["summary"]["SF"]["n_channels"]
                        print(f"  [DONE] Run {rnum} ({res_item['category']}): DS N={ds_n}, SF N={sf_n}")
        else:
            for task_args in tasks:
                res_item = _worker_process_run(task_args)
                if res_item is not None:
                    all_runs_summary.append(res_item)
                    rnum = res_item["run"]
                    ds_n = res_item["summary"]["DS"]["n_channels"]
                    sf_n = res_item["summary"]["SF"]["n_channels"]
                    print(f"  [DONE] Run {rnum} ({res_item['category']}): DS N={ds_n}, SF N={sf_n}")

        master_json = os.path.join(out_dir, "all_runs_cscint_summary.json")
        all_runs_summary.sort(key=lambda d: d["run"])
        with open(master_json, "w") as jf:
            json.dump(all_runs_summary, jf, indent=2)
        print(f"[SUCCESS] Consolidated summary for {len(all_runs_summary)} runs saved to {master_json}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
