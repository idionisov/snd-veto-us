#!/usr/bin/env python3
"""
fit_cscint.py
-------------
Extracts the effective scintillator speed c_scint, its statistical fit error,
and its systematic error for each SiPM channel from merged cscint ROOT files.

Supported Subsystems & Geometry:
  - Horizontal Veto (detID 10000..11999): fit in x in [-42, -12] cm, both ends (0..7 Right, 8..15 Left).
  - Vertical Veto Plane 2 (detID 12000..12999, 2024+): fit in y in [13, 55] cm, top readout (0..7).
  - Upstream (detID 20000..24999): fit in x in [-55, -5] cm, both ends (0..7 Right, 8..15 Left).
  - Downstream Horizontal (detID 30000..32999, bar < 60): fit in x in [-55, -5] cm, ch 0 (Left), ch 1 (Right).
  - Downstream Vertical (detID 30000..33999, bar >= 60): fit in y in [10, 66] cm, top readout (ch 0).

Features:
  - Linear fit of dt vs position with stat and systematic uncertainties.
  - Generates 2-pad canvases:
      Top pad: 2D histogram + fitted line + data points with stat & syst errors + legend
               with chi2/ndf, measured c_scint, stat and syst errors.
      Bottom pad: Data / Fit ratio with stat and syst errors drawn as hatched bands.
  - Sub-TDirectory for each SiPM containing slice projection histograms and Gaussian fits.
  - In gaussian_fits_DS and gaussian_fits_SF directories:
      * Chi2ndf distribution across all slices and SiPMs combined.
      * Distribution of Gaussian fit stdev (sigma) values.
      * Graph with SiPM channel & slice on x-axis, Gaussian mean +/- stdev on y-axis.
  - In cscint_summary_DS and cscint_summary_SF directories (and ROOT top-level):
      * cscint vs detId (Veto, US, and DS together)
        with calculated errors as error bars and detector division markers.
      * cscint fit chi2ndf distribution.
      * cscint value and error distributions (total, stat, syst, and per-subsystem summary).
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
import subprocess
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


def get_channel_config(det_id: int, sipm: int):
    """
    Returns (subsystem_name, fit_min, fit_max, side_sign, is_vertical, n_segments)
    Subsystems:
      - Veto hor (detID 10000..11999): fit [-42.0, -12.0], side_sign: +1.0 (sipm < 8) / -1.0 (sipm >= 8), n_seg=3
      - Veto ver (detID 12000..12999): fit [13.0, 55.0], side_sign: +1.0 (top readout), is_vert=True, n_seg=3
      - US hor (detID 20000..24999): fit [-55.0, -5.0], side_sign: +1.0 (sipm < 8) / -1.0 (sipm >= 8), n_seg=5
      - DS hor (detID 30000..32999, bar < 60): fit [-55.0, -5.0], side_sign: -1.0 (sipm==0, Left) / +1.0 (sipm==1, Right), n_seg=5
      - DS ver (detID 30000..33999, bar >= 60): fit [10.0, 66.0], side_sign: +1.0 (top readout), is_vert=True, n_seg=5
    """
    subsys = det_id // 10000
    pl = (det_id % 10000) // 1000
    bar = det_id % 1000

    if subsys == 1:
        if pl >= 2:
            return "Veto", 13.0, 55.0, 1.0, True, 3
        else:
            side_sign = 1.0 if sipm < 8 else -1.0
            return "Veto", -42.0, -12.0, side_sign, False, 3
    elif subsys == 2:
        side_sign = 1.0 if sipm < 8 else -1.0
        return "US", -55.0, -5.0, side_sign, False, 5
    elif subsys == 3:
        if bar >= 60:
            return "DS", 10.0, 66.0, 1.0, True, 5
        else:
            side_sign = -1.0 if sipm == 0 else 1.0
            return "DS", -55.0, -5.0, side_sign, False, 5
    else:
        side_sign = 1.0 if sipm < 8 else -1.0
        return "Unknown", -55.0, -5.0, side_sign, False, 5


def fit_single_2d_hist(h2, ref="DS", sipm=0, ch_name="", fit_min=-55.0, fit_max=-5.0,
                       side_sign=1.0, min_slice_entries=15, collect_slices=True, n_segments=5):
    """
    Fits c_scint for a single 2D histogram h2 (x_pred or y_pred vs dt).
    Also extracts vertical slice projection histograms, Gaussian fits, and slice statistics.
    """
    if h2 is None or h2.GetEntries() < 100:
        return None

    gr = ROOT.TGraphErrors()

    ip = 0
    slices_data = []
    slice_stats_data = []

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
        chi2_g = 0.0
        ndf_g = 1
        sigma_g = max(0.3, rms)
        if int(res_g) == 0 and 0 < fg.GetParError(1) < 2.5:
            p1 = fg.GetParameter(1)
            if mode - 2.5 < p1 < mode + 2.5:
                mpv = p1
                mpv_err = fg.GetParError(1)
                fit_ok = True
                chi2_g = fg.GetChisquare()
                ndf_g = max(1, fg.GetNDF())
                sigma_g = abs(fg.GetParameter(2))

        if mpv is None:
            mpv = mode
            mpv_err = py.GetBinWidth(max_bin) / (12.0 ** 0.5)

        gr.SetPoint(ip, x, mpv)
        gr.SetPointError(ip, 0.0, mpv_err)
        ip += 1

        slice_stats_data.append({
            "bx": bx,
            "x": x,
            "mean": float(mpv),
            "mean_err": float(mpv_err),
            "sigma": float(sigma_g),
            "chi2_ndf": float(chi2_g / ndf_g) if fit_ok else None,
            "fit_ok": fit_ok,
            "ch_name": ch_name,
            "sipm": sipm,
        })

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

    # Systematic error: disjoint sub-segment fits (same as TimeWalk.py)
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
        "slice_stats": slice_stats_data,
    }


def build_cscint_canvas(h2, fixed_ch: str, ref: str, fit_res: dict, fit_min: float, fit_max: float, is_vertical: bool = False):
    """
    Constructs a 2-pad canvas containing:
      Top pad: 2D histogram + slice data points (stat error) + total uncertainty band + linear fit line.
               Legend displaying chi2/ndf, c_scint, stat and syst errors.
      Bottom pad: Data / Fit ratio with stat and syst errors drawn as hatched areas.
    """
    ROOT.TH1.AddDirectory(False)
    pos_axis = "y" if is_vertical else "x"
    pos_title = f"{pos_axis}_{{predicted}} [cm]"
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
    g_ratio_tot.SetTitle(f";{pos_title};Data / Fit")
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


def build_slice_summary_plots(slice_stats_list, ref="DS"):
    """
    Builds:
      - Chi2ndf distribution from all slice fits (from all SiPMs and all slices together)
      - Distribution of Gaussian fit stdev (sigma) values
      - A graph with SiPM number and slice on x-axis, Gaussian mean +/- stdev on y-axis
      - Multi-pad summary canvas
    """
    ROOT.TH1.AddDirectory(False)
    h_chi2 = ROOT.TH1D(f"h_slices_chi2ndf_{ref}", f"Slice Gaussian Fits #chi^{{2}}/ndf ({ref});#chi^{{2}}/ndf;Slices", 60, 0.0, 6.0)
    h_sigma = ROOT.TH1D(f"h_slices_stdev_{ref}", f"Slice Gaussian Fits StDev #sigma ({ref});#sigma [ns];Slices", 60, 0.0, 3.0)
    h_chi2.SetLineColor(ROOT.kAzure + 2)
    h_chi2.SetFillColorAlpha(ROOT.kAzure + 1, 0.35)
    h_sigma.SetLineColor(ROOT.kTeal + 2)
    h_sigma.SetFillColorAlpha(ROOT.kTeal + 1, 0.35)

    gr_mean_sigma = ROOT.TGraphErrors()
    gr_mean_sigma.SetName(f"gr_slices_mean_sigma_{ref}")
    gr_mean_sigma.SetTitle(f"Gaussian Mean #pm #sigma vs SiPM Channel & Slice ({ref});SiPM Channel Index;Mean #pm #sigma [ns]")
    gr_mean_sigma.SetMarkerStyle(20)
    gr_mean_sigma.SetMarkerSize(0.35)
    gr_mean_sigma.SetMarkerColor(ROOT.kBlue + 2)
    gr_mean_sigma.SetLineColor(ROOT.kAzure - 4)

    unique_channels = sorted(list(set(s["ch_name"] for s in slice_stats_list if s.get("ch_name"))))
    ch_to_idx = {ch: i for i, ch in enumerate(unique_channels)}

    bx_vals = [s["bx"] for s in slice_stats_list]
    min_bx = min(bx_vals) if bx_vals else 1
    max_bx = max(bx_vals) if bx_vals else 60
    bx_span = max(1, max_bx - min_bx + 1)

    ip = 0
    for s in slice_stats_list:
        if s.get("chi2_ndf") is not None:
            h_chi2.Fill(s["chi2_ndf"])
        h_sigma.Fill(s["sigma"])

        ch = s.get("ch_name", "")
        ch_idx = ch_to_idx.get(ch, s.get("sipm", 0))
        x_val = ch_idx + float(s["bx"] - min_bx) / float(bx_span)
        gr_mean_sigma.SetPoint(ip, x_val, s["mean"])
        gr_mean_sigma.SetPointError(ip, 0.0, s["sigma"])
        ip += 1

    cname = f"c_slices_summary_{ref}"
    canv = ROOT.TCanvas(cname, f"Slice Gaussian Fits Summary ({ref})", 1200, 800)
    pad1 = ROOT.TPad(f"pad1_{cname}", "Chi2ndf", 0.0, 0.48, 0.5, 1.0)
    pad2 = ROOT.TPad(f"pad2_{cname}", "StDev", 0.5, 0.48, 1.0, 1.0)
    pad3 = ROOT.TPad(f"pad3_{cname}", "MeanSigma", 0.0, 0.0, 1.0, 0.48)
    ROOT.SetOwnership(pad1, False)
    ROOT.SetOwnership(pad2, False)
    ROOT.SetOwnership(pad3, False)

    pad1.SetGrid()
    pad2.SetGrid()
    pad3.SetGrid()

    pad1.Draw()
    pad2.Draw()
    pad3.Draw()

    pad1.cd()
    h_chi2.Draw("HIST")

    pad2.cd()
    h_sigma.Draw("HIST")

    pad3.cd()
    gr_mean_sigma.Draw("AP")

    canv.Update()
    return {
        "h_chi2": h_chi2,
        "h_sigma": h_sigma,
        "gr_mean_sigma": gr_mean_sigma,
        "canvas": canv
    }


def build_cscint_global_summary_plots(channel_results, ref="DS"):
    """
    Builds:
      - cscint vs detId (US and Veto together, no gap between 1XXXX and 2XXXX)
      - cscint fit chi2ndf distribution
      - cscint value and error distributions (total, stat, syst)
      - Canvases for standalone detID inspection and 4-pad consolidated overview
    """
    ROOT.TH1.AddDirectory(False)
    det_ids = sorted(list(set(d["detID"] for d in channel_results.values())))
    n_bars = len(det_ids)
    det_to_idx = {det: i for i, det in enumerate(det_ids)}

    gr_veto = ROOT.TGraphErrors()
    gr_veto.SetName(f"gr_cscint_veto_{ref}")
    gr_veto.SetTitle(f"c_{{scint}} vs Detector ID ({ref});Detector ID;c_{{scint}} [cm/ns]")
    gr_veto.SetMarkerStyle(20)
    gr_veto.SetMarkerSize(0.6)
    gr_veto.SetMarkerColor(ROOT.kRed + 1)
    gr_veto.SetLineColor(ROOT.kRed + 1)

    gr_us = ROOT.TGraphErrors()
    gr_us.SetName(f"gr_cscint_us_{ref}")
    gr_us.SetTitle(f"c_{{scint}} vs Detector ID ({ref});Detector ID;c_{{scint}} [cm/ns]")
    gr_us.SetMarkerStyle(21)
    gr_us.SetMarkerSize(0.6)
    gr_us.SetMarkerColor(ROOT.kAzure + 2)
    gr_us.SetLineColor(ROOT.kAzure + 2)

    gr_ds = ROOT.TGraphErrors()
    gr_ds.SetName(f"gr_cscint_ds_{ref}")
    gr_ds.SetTitle(f"c_{{scint}} vs Detector ID ({ref});Detector ID;c_{{scint}} [cm/ns]")
    gr_ds.SetMarkerStyle(22)
    gr_ds.SetMarkerSize(0.6)
    gr_ds.SetMarkerColor(ROOT.kTeal + 2)
    gr_ds.SetLineColor(ROOT.kTeal + 2)

    gr_det_mean = ROOT.TGraphErrors()
    gr_det_mean.SetName(f"gr_cscint_det_mean_{ref}")
    gr_det_mean.SetTitle(f"Detector Bar Mean c_{{scint}} ({ref});Detector ID;c_{{scint}} [cm/ns]")
    gr_det_mean.SetMarkerStyle(29)
    gr_det_mean.SetMarkerSize(1.2)
    gr_det_mean.SetMarkerColor(ROOT.kBlack)
    gr_det_mean.SetLineColor(ROOT.kBlack)

    gr_all = ROOT.TGraphErrors()
    gr_all.SetName(f"gr_cscint_vs_detID_{ref}")
    gr_all.SetTitle(f"c_{{scint}} vs Detector ID ({ref});Detector ID;c_{{scint}} [cm/ns]")

    h_chi2 = ROOT.TH1D(f"h_cscint_chi2ndf_{ref}", f"c_{{scint}} Linear Fit #chi^{{2}}/ndf ({ref});#chi^{{2}}/ndf;Channels", 50, 0.0, 5.0)
    h_chi2.SetLineColor(ROOT.kRed + 1)
    h_chi2.SetFillColorAlpha(ROOT.kRed - 9, 0.4)

    h_val = ROOT.TH1D(f"h_cscint_val_{ref}", f"Effective Speed c_{{scint}} ({ref});c_{{scint}} [cm/ns];Channels", 50, 10.0, 18.0)
    h_val.SetLineColor(ROOT.kBlue + 2)
    h_val.SetFillColorAlpha(ROOT.kAzure - 9, 0.4)

    h_err_tot = ROOT.TH1D(f"h_cscint_err_tot_{ref}", f"Total Error #Delta c_{{scint}} ({ref});#Delta c [cm/ns];Channels", 50, 0.0, 1.2)
    h_err_tot.SetLineColor(ROOT.kBlack)
    h_err_tot.SetLineWidth(2)

    h_err_stat = ROOT.TH1D(f"h_cscint_err_stat_{ref}", f"Stat Error #Delta c_{{scint}}^{{stat}} ({ref});#Delta c [cm/ns];Channels", 50, 0.0, 1.2)
    h_err_stat.SetLineColor(ROOT.kOrange + 7)
    h_err_stat.SetLineWidth(2)
    h_err_stat.SetLineStyle(2)

    h_err_syst = ROOT.TH1D(f"h_cscint_err_syst_{ref}", f"Syst Error #Delta c_{{scint}}^{{syst}} ({ref});#Delta c [cm/ns];Channels", 50, 0.0, 1.2)
    h_err_syst.SetLineColor(ROOT.kTeal + 2)
    h_err_syst.SetLineWidth(2)
    h_err_syst.SetLineStyle(3)

    iv = 0
    iu = 0
    ids = 0
    ia = 0
    bar_groups = {}

    for k, d in channel_results.items():
        det = d["detID"]
        sipm = d["sipm"]
        c_val = d["c_scint"]
        c_err = d["delta_c_tot"]
        c_stat = d["delta_c_fit"]
        c_syst = d["delta_c_syst"]
        chi2_ndf = d["chi2_ndf"]

        h_chi2.Fill(chi2_ndf)
        h_val.Fill(c_val)
        h_err_tot.Fill(c_err)
        h_err_stat.Fill(c_stat)
        h_err_syst.Fill(c_syst)

        if det not in bar_groups:
            bar_groups[det] = []
        bar_groups[det].append((c_val, c_err))

        base_x = det_to_idx[det]
        x = base_x + (sipm - 7.5) / 18.0

        if det < 20000:
            gr_veto.SetPoint(iv, x, c_val)
            gr_veto.SetPointError(iv, 0.0, c_err)
            iv += 1
        elif det < 30000:
            gr_us.SetPoint(iu, x, c_val)
            gr_us.SetPointError(iu, 0.0, c_err)
            iu += 1
        else:
            gr_ds.SetPoint(ids, x, c_val)
            gr_ds.SetPointError(ids, 0.0, c_err)
            ids += 1

        gr_all.SetPoint(ia, x, c_val)
        gr_all.SetPointError(ia, 0.0, c_err)
        ia += 1

    ib = 0
    for det in det_ids:
        pts = bar_groups.get(det, [])
        if not pts:
            continue
        vals = np.array([p[0] for p in pts])
        errs = np.array([p[1] for p in pts])
        w = 1.0 / (errs ** 2)
        w_mean = float(np.sum(w * vals) / np.sum(w))
        w_err = float(1.0 / np.sqrt(np.sum(w)))
        gr_det_mean.SetPoint(ib, det_to_idx[det], w_mean)
        gr_det_mean.SetPointError(ib, 0.0, w_err)
        ib += 1

    # Standalone cscint vs detID canvas
    c_det = ROOT.TCanvas(f"c_cscint_vs_detID_{ref}", f"c_scint vs Detector ID ({ref})", 1400, 650)
    c_det.SetGrid()
    c_det.SetLeftMargin(0.08)
    c_det.SetRightMargin(0.04)
    c_det.SetBottomMargin(0.18)

    h_axis = ROOT.TH1F(f"h_axis_{ref}", f"Effective Scintillator Speed c_{{scint}} vs Detector ID ({ref});Detector ID;c_{{scint}} [cm/ns]", n_bars, -0.5, n_bars - 0.5)
    h_axis.SetDirectory(0)
    h_axis.SetStats(0)
    h_axis.GetYaxis().SetRangeUser(10.0, 18.0)
    h_axis.GetXaxis().SetTitleOffset(1.3)
    h_axis.GetXaxis().SetLabelSize(0.028)

    veto_count = sum(1 for d in det_ids if d < 20000)
    us_count = sum(1 for d in det_ids if 20000 <= d < 30000)
    ds_count = sum(1 for d in det_ids if d >= 30000)

    label_step = max(1, n_bars // 30)
    for i, det in enumerate(det_ids):
        is_boundary = (det in (10000, 11000, 12000, 20000, 21000, 22000, 23000, 24000, 30000, 31000, 32000, 33000))
        if i % label_step == 0 or is_boundary:
            h_axis.GetXaxis().SetBinLabel(i + 1, str(det))
        else:
            h_axis.GetXaxis().SetBinLabel(i + 1, "")
    h_axis.GetXaxis().LabelsOption("v")
    h_axis.Draw("AXIS")

    lines = []
    labels = []

    # Separation line between Veto and US
    if veto_count > 0 and us_count > 0:
        l_vus = ROOT.TLine(veto_count - 0.5, 10.0, veto_count - 0.5, 18.0)
        l_vus.SetLineStyle(7)
        l_vus.SetLineColor(ROOT.kGray + 2)
        l_vus.SetLineWidth(2)
        ROOT.SetOwnership(l_vus, False)
        l_vus.Draw()
        lines.append(l_vus)

    # Separation line between US and DS
    if us_count > 0 and ds_count > 0:
        l_usds = ROOT.TLine(veto_count + us_count - 0.5, 10.0, veto_count + us_count - 0.5, 18.0)
        l_usds.SetLineStyle(7)
        l_usds.SetLineColor(ROOT.kGray + 2)
        l_usds.SetLineWidth(2)
        ROOT.SetOwnership(l_usds, False)
        l_usds.Draw()
        lines.append(l_usds)

    if veto_count > 0:
        t_veto = ROOT.TLatex(max(0.5, veto_count / 2.0 - 0.5), 17.4, "VETO")
        ROOT.SetOwnership(t_veto, False)
        t_veto.SetTextAlign(22)
        t_veto.SetTextFont(62)
        t_veto.SetTextColor(ROOT.kRed + 2)
        t_veto.Draw()
        labels.append(t_veto)

    if us_count > 0:
        t_us = ROOT.TLatex(veto_count + us_count / 2.0 - 0.5, 17.4, "UPSTREAM (US)")
        ROOT.SetOwnership(t_us, False)
        t_us.SetTextAlign(22)
        t_us.SetTextFont(62)
        t_us.SetTextColor(ROOT.kAzure + 2)
        t_us.Draw()
        labels.append(t_us)

    if ds_count > 0:
        t_ds = ROOT.TLatex(veto_count + us_count + ds_count / 2.0 - 0.5, 17.4, "DOWNSTREAM (DS)")
        ROOT.SetOwnership(t_ds, False)
        t_ds.SetTextAlign(22)
        t_ds.SetTextFont(62)
        t_ds.SetTextColor(ROOT.kTeal + 2)
        t_ds.Draw()
        labels.append(t_ds)

    if iv > 0:
        gr_veto.Draw("PE SAME")
    if iu > 0:
        gr_us.Draw("PE SAME")
    if ids > 0:
        gr_ds.Draw("PE SAME")
    gr_det_mean.Draw("PE SAME")

    leg = ROOT.TLegend(0.12, 0.76, 0.45, 0.90)
    leg.SetBorderSize(1)
    leg.SetFillColorAlpha(ROOT.kWhite, 0.85)
    if iv > 0:
        leg.AddEntry(gr_veto, "Veto SiPMs", "lep")
    if iu > 0:
        leg.AddEntry(gr_us, "US SiPMs", "lep")
    if ids > 0:
        leg.AddEntry(gr_ds, "DS SiPMs", "lep")
    leg.AddEntry(gr_det_mean, "Bar Weighted Mean", "lep")
    ROOT.SetOwnership(leg, False)
    leg.Draw()
    c_det.Update()

    # 4-pad consolidated canvas
    c_summary = ROOT.TCanvas(f"c_cscint_summary_{ref}", f"c_scint Global Summary ({ref})", 1200, 850)
    c_summary.Divide(2, 2)

    c_summary.cd(1)
    ROOT.gPad.SetGrid()
    h_axis_clone = h_axis.Clone(f"h_axis_clone_{ref}")
    ROOT.SetOwnership(h_axis_clone, False)
    h_axis_clone.Draw("AXIS")
    for l_obj in lines:
        l_clone = l_obj.Clone()
        ROOT.SetOwnership(l_clone, False)
        l_clone.Draw()
    if iv > 0:
        gr_veto.Draw("PE SAME")
    if iu > 0:
        gr_us.Draw("PE SAME")
    if ids > 0:
        gr_ds.Draw("PE SAME")
    gr_det_mean.Draw("PE SAME")

    c_summary.cd(2)
    ROOT.gPad.SetGrid()
    h_val.Draw("HIST")

    c_summary.cd(3)
    ROOT.gPad.SetGrid()
    h_chi2.Draw("HIST")

    c_summary.cd(4)
    ROOT.gPad.SetGrid()
    h_err_tot.Draw("HIST")
    h_err_stat.Draw("HIST SAME")
    h_err_syst.Draw("HIST SAME")

    leg_err = ROOT.TLegend(0.55, 0.68, 0.88, 0.88)
    leg_err.SetBorderSize(1)
    leg_err.SetFillColorAlpha(ROOT.kWhite, 0.8)
    leg_err.AddEntry(h_err_tot, "Total Uncertainty", "l")
    leg_err.AddEntry(h_err_stat, "Stat Uncertainty", "l")
    leg_err.AddEntry(h_err_syst, "Syst Uncertainty", "l")
    ROOT.SetOwnership(leg_err, False)
    leg_err.Draw()

    c_summary.Update()

    return {
        "gr_veto": gr_veto,
        "gr_us": gr_us,
        "gr_all": gr_all,
        "gr_det_mean": gr_det_mean,
        "h_chi2": h_chi2,
        "h_val": h_val,
        "h_err_tot": h_err_tot,
        "h_err_stat": h_err_stat,
        "h_err_syst": h_err_syst,
        "c_det": c_det,
        "c_summary": c_summary
    }


def fit_file(root_path: str, save_canvas: bool = True, save_slices: bool = True,
             save_slice_canvases: bool = False, output_path: str = None, verbose: bool = False,
             veto_min: float = -42.0, veto_max: float = -12.0, veto_n_segments: int = 3):
    """
    Fits c_scint for all SiPM channels in root_path.
    If save_canvas=True, stores 2-pad fit canvas into each channel directory.
    If save_slices=True, stores vertical slice projection histograms and Gaussian fits.
    Also produces slice summary and global cscint distributions across all SiPMs.
    """
    target_path = output_path if output_path else root_path
    mode = "UPDATE" if (save_canvas or save_slices) else "READ"
    is_network = root_path.startswith("/eos") or (target_path and target_path.startswith("/eos"))

    if is_network and mode == "UPDATE":
        tmp_fd, work_file = tempfile.mkstemp(suffix=".root", prefix="cscint_fit_")
        os.close(tmp_fd)
        if shutil.which("xrdcp") and "/eos/" in root_path:
            server = "root://eosuser.cern.ch/" if "/eos/user/" in root_path else "root://eospublic.cern.ch/"
            subpath = root_path if root_path.startswith("/eos/") else f"/eos/{root_path}"
            subprocess.run(["xrdcp", "-f", f"{server}{subpath}", work_file], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            shutil.copyfile(root_path, work_file)
    elif mode == "READ" and root_path.startswith("/eos/user/"):
        work_file = f"root://eosuser.cern.ch/{root_path}"
    elif mode == "READ" and root_path.startswith("/eos/experiment/"):
        work_file = f"root://eospublic.cern.ch/{root_path}"
    else:
        work_file = target_path if (output_path and output_path != root_path) else root_path
        if output_path and output_path != root_path and mode == "UPDATE":
            shutil.copyfile(root_path, work_file)

    f = ROOT.TFile.Open(work_file, mode)
    if not f or f.IsZombie():
        print(f"[ERROR] Cannot open ROOT file: {work_file}", file=sys.stderr)
        if is_network and os.path.exists(work_file):
            os.remove(work_file)
        return None

    results = {"DS": {}, "SF": {}}
    all_slice_stats = {"DS": [], "SF": []}

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

        subsys_name, fit_min_default, fit_max_default, side_sign, is_vert, n_seg = get_channel_config(detID, sipm)

        # Allow user override for veto bounds if horizontal veto
        if subsys_name == "Veto" and not is_vert:
            fit_min_ds, fit_max_ds = veto_min, veto_max
            fit_min_sf, fit_max_sf = veto_min, veto_max
            n_seg = veto_n_segments
        else:
            fit_min_ds, fit_max_ds = fit_min_default, fit_max_default
            fit_min_sf, fit_max_sf = fit_min_default, fit_max_default

        # Fit DS
        h2_ds = f.Get(f"{k}/dt-DS")
        if h2_ds and h2_ds.InheritsFrom("TH2"):
            res_ds = fit_single_2d_hist(
                h2_ds, ref="DS", sipm=sipm, ch_name=k, fit_min=fit_min_ds, fit_max=fit_max_ds,
                side_sign=side_sign, min_slice_entries=15, collect_slices=save_slices, n_segments=n_seg
            )
            if res_ds is not None:
                if save_canvas:
                    canv_ds = build_cscint_canvas(h2_ds, k, "DS", res_ds, fit_min=fit_min_ds, fit_max=fit_max_ds, is_vertical=is_vert)
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

                if res_ds.get("slice_stats"):
                    all_slice_stats["DS"].extend(res_ds["slice_stats"])

                res_ds.pop("slices", None)
                res_ds.pop("slice_stats", None)
                for arr_k in ("x_arr", "y_arr", "ey_arr"):
                    res_ds.pop(arr_k, None)
                res_ds["sipm"] = sipm
                res_ds["detID"] = detID
                res_ds["subsystem"] = subsys_name
                res_ds["is_vertical"] = is_vert
                results["DS"][k] = res_ds

        # Fit SF
        h2_sf = f.Get(f"{k}/dt-SF")
        if h2_sf and h2_sf.InheritsFrom("TH2"):
            res_sf = fit_single_2d_hist(
                h2_sf, ref="SF", sipm=sipm, ch_name=k, fit_min=fit_min_sf, fit_max=fit_max_sf,
                side_sign=side_sign, min_slice_entries=15, collect_slices=save_slices, n_segments=n_seg
            )
            if res_sf is not None:
                if save_canvas:
                    canv_sf = build_cscint_canvas(h2_sf, k, "SF", res_sf, fit_min=fit_min_sf, fit_max=fit_max_sf, is_vertical=is_vert)
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

                if res_sf.get("slice_stats"):
                    all_slice_stats["SF"].extend(res_sf["slice_stats"])

                res_sf.pop("slices", None)
                res_sf.pop("slice_stats", None)
                for arr_k in ("x_arr", "y_arr", "ey_arr"):
                    res_sf.pop(arr_k, None)
                res_sf["sipm"] = sipm
                res_sf["detID"] = detID
                res_sf["subsystem"] = subsys_name
                res_sf["is_vertical"] = is_vert
                results["SF"][k] = res_sf

        if verbose and (idx + 1) % 100 == 0:
            print(f"  Processed {idx + 1}/{total_ch} channels...", flush=True)

    # Write global slice distributions and cscint summary distributions
    if save_slices or save_canvas:
        for ref in ("DS", "SF"):
            # 1. Global slice summary in gaussian_fits_<ref>
            if all_slice_stats[ref]:
                s_plots = build_slice_summary_plots(all_slice_stats[ref], ref=ref)
                g_dir = f.GetDirectory(f"gaussian_fits_{ref}")
                if not g_dir:
                    g_dir = f.mkdir(f"gaussian_fits_{ref}")
                g_dir.cd()
                g_dir.WriteObject(s_plots["h_chi2"], s_plots["h_chi2"].GetName(), "kOverwrite")
                g_dir.WriteObject(s_plots["h_sigma"], s_plots["h_sigma"].GetName(), "kOverwrite")
                g_dir.WriteObject(s_plots["gr_mean_sigma"], s_plots["gr_mean_sigma"].GetName(), "kOverwrite")
                g_dir.WriteObject(s_plots["canvas"], s_plots["canvas"].GetName(), "kOverwrite")
                s_plots["canvas"].Close()

            # 2. Global cscint summary in cscint_summary_<ref> and root level
            if results[ref]:
                c_plots = build_cscint_global_summary_plots(results[ref], ref=ref)
                c_dir = f.GetDirectory(f"cscint_summary_{ref}")
                if not c_dir:
                    c_dir = f.mkdir(f"cscint_summary_{ref}")
                c_dir.cd()
                for obj_key in ("gr_veto", "gr_us", "gr_ds", "gr_all", "gr_det_mean", "h_chi2", "h_val",
                                "h_err_tot", "h_err_stat", "h_err_syst", "c_det", "c_summary"):
                    if obj_key in c_plots:
                        obj = c_plots[obj_key]
                        c_dir.WriteObject(obj, obj.GetName(), "kOverwrite")

                f.cd()
                f.WriteObject(c_plots["c_det"], c_plots["c_det"].GetName(), "kOverwrite")
                f.WriteObject(c_plots["c_summary"], c_plots["c_summary"].GetName(), "kOverwrite")
                c_plots["c_det"].Close()
                c_plots["c_summary"].Close()

    f.Close()

    if is_network and mode == "UPDATE":
        os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
        if shutil.which("xrdcp") and "/eos/" in target_path:
            server = "root://eosuser.cern.ch/" if "/eos/user/" in target_path else "root://eospublic.cern.ch/"
            subpath = target_path if target_path.startswith("/eos/") else f"/eos/{target_path}"
            subprocess.run(["xrdcp", "-f", work_file, f"{server}{subpath}"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(work_file):
                os.remove(work_file)
        else:
            shutil.move(work_file, target_path)

    # Calculate summary statistics
    summary = {}
    for ref in ("DS", "SF"):
        c_vals = [d["c_scint"] for d in results[ref].values()]
        c_errs = [d["delta_c_tot"] for d in results[ref].values()]
        subsys_summary = {}
        for sub_name in ("Veto", "US", "DS"):
            sub_vals = [d["c_scint"] for d in results[ref].values() if d.get("subsystem") == sub_name]
            sub_errs = [d["delta_c_tot"] for d in results[ref].values() if d.get("subsystem") == sub_name]
            if sub_vals:
                sw = 1.0 / (np.array(sub_errs) ** 2)
                subsys_summary[sub_name] = {
                    "n_channels": len(sub_vals),
                    "mean": float(np.mean(sub_vals)),
                    "std": float(np.std(sub_vals)),
                    "weighted_mean": float(np.sum(sw * np.array(sub_vals)) / np.sum(sw)),
                    "weighted_sem": float(1.0 / np.sqrt(np.sum(sw))),
                }
            else:
                subsys_summary[sub_name] = {"n_channels": 0, "mean": None, "std": None, "weighted_mean": None, "weighted_sem": None}

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
                "subsystems": subsys_summary,
            }
        else:
            summary[ref] = {"n_channels": 0, "mean": None, "std": None, "weighted_mean": None, "weighted_sem": None, "subsystems": subsys_summary}

    results["summary"] = summary
    return results


def _worker_process_run(task_args):
    """Worker task wrapper for multiprocessing."""
    fpath, rnum, cat, out_run_json, out_run_root, save_canvas, save_slices, save_slice_canvases, verbose, veto_min, veto_max, veto_n_seg = task_args
    try:
        res = fit_file(
            fpath,
            save_canvas=save_canvas,
            save_slices=save_slices,
            save_slice_canvases=save_slice_canvases,
            output_path=out_run_root,
            verbose=verbose,
            veto_min=veto_min,
            veto_max=veto_max,
            veto_n_segments=veto_n_seg
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
    parser.add_argument("--no-canvas", dest="save_canvas", action="store_false", default=True,
                        help="Do not store fit canvases in the input ROOT file")
    parser.add_argument("--output-root-dir", type=str, default=None,
                        help="Optional output directory for modified ROOT files (default: update in-place)")
    parser.add_argument("--veto-min", type=float, default=-42.0,
                        help="Lower bound in x_pred [cm] for Veto c_scint fit (default: -42.0)")
    parser.add_argument("--veto-max", type=float, default=-12.0,
                        help="Upper bound in x_pred [cm] for Veto c_scint fit (default: -12.0)")
    parser.add_argument("--veto-segments", type=int, default=3,
                        help="Number of sub-segments for Veto systematic error estimation (default: 3)")
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
            verbose=args.verbose,
            veto_min=args.veto_min,
            veto_max=args.veto_max,
            veto_n_segments=args.veto_segments
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
                print(f"[SUCCESS] Saved fit canvases, slice subdirectories, and global summary plots into ROOT file: {target_written}")

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
                args.save_canvas, args.save_slices, args.save_slice_canvases, args.verbose,
                args.veto_min, args.veto_max, args.veto_segments
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
