#!/usr/bin/env python3
"""
fit_timewalk.py
---------------
Extracts Time-Walk calibration constants (5-parameter rational function),
systematic uncertainty floors (via NLL minimization), and fine time alignment
constants (d_SiPM) from merged Time-Walk ROOT files.

Model (TimeWalk.py & Thesis Eq. 4.1.9):
  dt^TW(QDC) = t0 + alpha / (beta * QDC - QDC0) + gamma * QDC

Features:
  - Fits both DS and SF reference time-walk distributions (dtvqdc-DS and dtvqdc-SF).
  - 2-Pad Canvas per channel:
      Top pad: 2D histogram + slice data points (stat SEM) + total & syst uncertainty bands
               + fitted rational function + legend with parameters, chi2/ndf, sigma_sys, RMS res.
      Bottom pad: Data / Fit ratio panel with stat and syst uncertainties displayed as hatched bands.
  - Fine time-alignment constant extraction (d_SiPM +/- err) via truncated mean of residual.
  - Summary distributions across all channels:
      * chi2/ndf (statistical & total)
      * sigma_sys systematic uncertainty floor
      * RMS residual
      * Rational function parameter distributions (t0, alpha, beta, QDC0, gamma)
      * Global alignment graph d_SiPM vs detID (US & Veto contiguous, without numeric gap).
  - Consolidated JSON output: Contains all timewalk parameters, alignment constants,
    and automatically embeds the corresponding c_scint constants from /eos/user/i/idioniso/Timing/cscint/fits/.
  - Multi-processing support and category filtering (catI, catII, catIII).

Usage:
  ./fit_timewalk.py -i /eos/user/i/idioniso/Timing/timewalk/runs/run5119.root -o run5119_timing_calibration.json
  ./fit_timewalk.py --input-dir /eos/user/i/idioniso/Timing/timewalk/runs -c catII -j 8
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
from scipy.optimize import curve_fit, minimize_scalar

try:
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError
except ImportError:
    print("[ERROR] PyROOT is required to execute fit_timewalk.py", file=sys.stderr)
    sys.exit(1)


# ==============================================================================
# Model Functions (matching TimeWalk.py)
# ==============================================================================

def tw_func(qdc, t0, alpha, beta, qdc0, gamma):
    """5-parameter rational time-walk function."""
    denom = beta * qdc - qdc0
    denom = np.where(denom <= 1e-4, 1e-4, denom)
    return t0 + alpha / denom + gamma * qdc


def nll_objective(sigma_sys, x_data, y_data, sigma_stat, params):
    """Negative log-likelihood objective to determine systematic error floor sigma_sys."""
    y_pred = tw_func(x_data, *params)
    var_total = sigma_stat ** 2 + sigma_sys ** 2
    return 0.5 * np.sum(((y_data - y_pred) ** 2) / var_total + np.log(var_total))


def set_canvas_palette(name="jet"):
    """Configures ROOT color palette to jet/rainbow, plasma, viridis, etc."""
    name_lower = str(name).lower()
    if name_lower in ("jet", "rainbow", "krainbow"):
        ROOT.gStyle.SetPalette(ROOT.kRainBow)
        ROOT.gStyle.SetNumberContours(255)
    elif name_lower in ("viridis", "kviridis"):
        ROOT.gStyle.SetPalette(ROOT.kViridis)
        ROOT.gStyle.SetNumberContours(255)
    else:
        try:
            import matplotlib
            cmap = matplotlib.colormaps[name_lower]
            n_points = 255
            stops = np.linspace(0.0, 1.0, 12)
            red, green, blue = [], [], []
            for s in stops:
                r, g, b, _ = cmap(s)
                red.append(r)
                green.append(g)
                blue.append(b)
            red = np.array(red, dtype=float)
            green = np.array(green, dtype=float)
            blue = np.array(blue, dtype=float)
            stops = np.array(stops, dtype=float)
            ROOT.TColor.CreateGradientColorTable(len(stops), stops, red, green, blue, n_points)
            ROOT.gStyle.SetNumberContours(n_points)
        except Exception:
            ROOT.gStyle.SetPalette(ROOT.kRainBow)
            ROOT.gStyle.SetNumberContours(255)


def get_run_category(run_nr: int) -> str:
    """Determines category based on run number."""
    if run_nr <= 5116 or (5175 <= run_nr <= 5192):
        return "catI"
    elif (5117 <= run_nr <= 5174) or (5193 <= run_nr <= 5412):
        return "catII"
    else:
        return "catIII"


def normalize_categories(cat_args):
    """Normalizes category arguments into a set of standard category strings."""
    if not cat_args:
        return {"catI", "catII", "catIII"}
    if isinstance(cat_args, str):
        cat_args = [cat_args]
    res = set()
    for c in cat_args:
        c_str = str(c).strip().upper()
        if c_str in ("ALL", "*"):
            return {"catI", "catII", "catIII"}
        if c_str in ("I", "CATI"):
            res.add("catI")
        elif c_str in ("II", "CATII"):
            res.add("catII")
        elif c_str in ("III", "CATIII"):
            res.add("catIII")
        else:
            res.add(str(c).strip().lower())
    return res


# ==============================================================================
# Channel Fitting Logic
# ==============================================================================

def fit_single_timewalk_hist(
    h2,
    ref: str,
    fixed_ch: str,
    qdc_min: float = 1.0,
    min_bin_entries: int = 10,
    min_total_entries: int = 200
):
    """
    Fits the 5-parameter rational time-walk model to a single 2D histogram.
    Returns dictionary with fit results, or None if fitting fails / criteria unmet.
    """
    if not h2 or not h2.InheritsFrom("TH2"):
        return None

    entries = h2.GetEntries()
    is_sf = (ref == "SF")
    threshold = 150 if is_sf else min_total_entries
    if entries < threshold:
        return None

    nbins = h2.GetNbinsX()
    x_pts, y_pts, ey_pts = [], [], []

    # 1. Timing Projections per QDC bin: Extract MPV and SEM
    for b in range(1, nbins + 1):
        x_val = h2.GetXaxis().GetBinCenter(b)
        if x_val < qdc_min:
            continue
        py = h2.ProjectionY(f"py_tw_{ref}_{fixed_ch}_{b}", b, b)
        bin_entries = py.GetEntries()
        if bin_entries < min_bin_entries:
            continue

        max_bin = py.GetMaximumBin()
        y_val = py.GetBinCenter(max_bin)
        rms_val = py.GetRMS()
        ey_val = rms_val / np.sqrt(bin_entries) if bin_entries > 0 else 0.0
        if ey_val <= 0:
            continue

        x_pts.append(x_val)
        y_pts.append(y_val)
        ey_pts.append(ey_val)

    min_pts_required = 6 if is_sf else 10
    if len(x_pts) < min_pts_required:
        return None

    x_arr = np.array(x_pts, dtype=float)
    y_arr = np.array(y_pts, dtype=float)
    ey_arr = np.array(ey_pts, dtype=float)

    qdc_min_fit = float(x_arr[0])
    qdc_max_fit = float(x_arr[-1])

    # 2. Fit 5-parameter rational function (Thesis Table 4.2 bounds)
    high_qdc_mask = x_arr > (0.6 * qdc_max_fit)
    t0_est = float(np.median(y_arr[high_qdc_mask])) if np.sum(high_qdc_mask) > 3 else float(y_arr[-1])

    p0 = [t0_est, -50.0, 5.0, -2.0, 0.005]
    bounds_lower = [0.5 * t0_est if t0_est > 0 else 1.5 * t0_est, -500.0, 0.01, -10.0, 0.0]
    bounds_upper = [1.5 * t0_est if t0_est > 0 else 0.5 * t0_est, 0.0, 30.0, 0.0, 1.0]

    try:
        popt, _ = curve_fit(tw_func, x_arr, y_arr, p0=p0, bounds=(bounds_lower, bounds_upper), maxfev=10000)
    except Exception:
        return None

    # 3. Systematic uncertainty floor optimization via NLL
    try:
        res_nll = minimize_scalar(nll_objective, bounds=(0.001, 1.0), method="bounded", args=(x_arr, y_arr, ey_arr, popt))
        sigma_sys = float(res_nll.x) if res_nll.success else 0.350
    except Exception:
        sigma_sys = 0.350

    t0, alpha, beta, qdc0, gamma = [float(v) for v in popt]
    y_fit = tw_func(x_arr, *popt)
    ey_tot = np.sqrt(ey_arr ** 2 + sigma_sys ** 2)
    ndf = max(1, len(x_arr) - 5)

    chi2_stat = float(np.sum(((y_arr - y_fit) ** 2) / (ey_arr ** 2)))
    chi2_stat_ndf = chi2_stat / ndf

    chi2_tot = float(np.sum(((y_arr - y_fit) ** 2) / (ey_tot ** 2)))
    chi2_tot_ndf = chi2_tot / ndf
    rms_res = float(np.sqrt(np.mean((y_arr / y_fit - 1.0) ** 2)))

    # 4. Fine alignment parameter extraction (d_SiPM) via truncated mean of residual
    if ref == "SF":
        h_res = ROOT.TH1F(f"dt_residual_{ref}_{fixed_ch}", f"{fixed_ch} TW-corrected residual ({ref});dt_{{SiPM}}^{{TW, ToF}} [ns];Counts", 500, -45.0, 5.0)
    else:
        h_res = ROOT.TH1F(f"dt_residual_{ref}_{fixed_ch}", f"{fixed_ch} TW-corrected residual ({ref});dt_{{SiPM}}^{{TW, ToF}} [ns];Counts", 350, -10.0, 25.0)
    h_res.SetDirectory(0)

    for bx in range(1, h2.GetNbinsX() + 1):
        qdc_c = h2.GetXaxis().GetBinCenter(bx)
        if qdc_c < qdc_min_fit or qdc_c > qdc_max_fit:
            continue
        denom_c = beta * qdc_c - qdc0
        if denom_c <= 1e-4:
            denom_c = 1e-4
        tw_val = (alpha / denom_c) + gamma * qdc_c

        for by in range(1, h2.GetNbinsY() + 1):
            cnt = h2.GetBinContent(bx, by)
            if cnt <= 0:
                continue
            dt_c = h2.GetYaxis().GetBinCenter(by)
            dt_res = dt_c - tw_val
            h_res.Fill(dt_res, cnt)

    if h_res.GetEntries() >= 10:
        max_bin = h_res.GetMaximumBin()
        t_mode = h_res.GetBinCenter(max_bin)
        std_dev = h_res.GetStdDev()
        low_bin = h_res.FindBin(t_mode - std_dev)
        high_bin = h_res.FindBin(t_mode + std_dev)
        sum_w = 0.0
        sum_wx = 0.0
        sum_wxx = 0.0
        for b in range(low_bin, high_bin + 1):
            w = h_res.GetBinContent(b)
            if w <= 0:
                continue
            x = h_res.GetBinCenter(b)
            sum_w += w
            sum_wx += w * x
            sum_wxx += w * x * x
        if sum_w > 0:
            d_val = float(sum_wx / sum_w)
            var = (sum_wxx / sum_w) - d_val ** 2
            sigma_trunc = float(np.sqrt(max(0.0, var)))
            d_unc = float(sigma_trunc / np.sqrt(sum_w))
        else:
            d_val = float(t0)
            d_unc = float(sigma_sys)
    else:
        d_val = float(t0)
        d_unc = float(sigma_sys)

    return {
        "x_arr": x_arr,
        "y_arr": y_arr,
        "ey_arr": ey_arr,
        "ey_tot": ey_tot,
        "y_fit": y_fit,
        "t0": t0,
        "alpha": alpha,
        "beta": beta,
        "qdc0": qdc0,
        "gamma": gamma,
        "sigma_sys": sigma_sys,
        "chi2_stat": chi2_stat,
        "chi2_stat_ndf": chi2_stat_ndf,
        "chi2_tot": chi2_tot,
        "chi2_tot_ndf": chi2_tot_ndf,
        "rms_residual": rms_res,
        "qdc_limits": [qdc_min_fit, qdc_max_fit],
        "alignment_d": d_val,
        "alignment_d_err": d_unc,
        "h_residual": h_res,
    }


# ==============================================================================
# 2-Pad Canvas Construction (matching fit_cscint.py style)
# ==============================================================================

def build_timewalk_canvas(h2, fixed_ch: str, ref: str, fit_res: dict, run_nr: int = 0, palette: str = "jet"):
    """
    Constructs a 2-pad canvas containing:
      Top pad: 2D histogram + data points (stat SEM) + total and syst uncertainty bands + rational fit curve.
               Legend displaying chi2/ndf, fit parameters, sigma_sys, and RMS residual.
               Z-axis plotted on logarithmic scale with custom palette (e.g. plasma, jet).
      Bottom pad: Data / Fit ratio with stat and syst errors drawn as hatched bands.
    """
    ROOT.TH1.AddDirectory(False)
    cname = f"c_timewalk_fit_{ref}_{fixed_ch}"
    c = ROOT.TCanvas(cname, f"Time-Walk Fit - Channel {fixed_ch} ({ref} Reference - Run {run_nr})", 1000, 850)

    pad1 = ROOT.TPad(f"pad1_{ref}_{fixed_ch}", "Upper Pad", 0.0, 0.28, 1.0, 1.0)
    pad2 = ROOT.TPad(f"pad2_{ref}_{fixed_ch}", "Lower Pad", 0.0, 0.0, 1.0, 0.28)
    ROOT.SetOwnership(pad1, False)
    ROOT.SetOwnership(pad2, False)

    pad1.SetBottomMargin(0.02)
    pad1.SetLeftMargin(0.12)
    pad1.SetRightMargin(0.14)
    pad1.SetGrid()
    pad1.SetLogz(1)

    pad2.SetTopMargin(0.03)
    pad2.SetBottomMargin(0.32)
    pad2.SetLeftMargin(0.12)
    pad2.SetRightMargin(0.14)
    pad2.SetGrid()

    pad1.Draw()
    pad2.Draw()

    x_arr = fit_res["x_arr"]
    y_arr = fit_res["y_arr"]
    ey_arr = fit_res["ey_arr"]
    ey_tot = fit_res["ey_tot"]
    y_fit = fit_res["y_fit"]
    n_pts = len(x_arr)
    dx_band = np.full(n_pts, 0.5)

    sigma_sys = fit_res["sigma_sys"]
    sigma_syst_arr = np.full(n_pts, sigma_sys)

    t0 = fit_res["t0"]
    alpha = fit_res["alpha"]
    beta = fit_res["beta"]
    qdc0 = fit_res["qdc0"]
    gamma = fit_res["gamma"]
    qdc_min_fit, qdc_max_fit = fit_res["qdc_limits"]
    x_max_plot = max(180.0, qdc_max_fit * 1.05)

    # Top Pad: 2D distribution + Data Points + Fit
    pad1.cd()
    set_canvas_palette(palette)
    h2_clone = h2.Clone(f"h2_dtvqdc_{ref}_{fixed_ch}_clone")
    ROOT.SetOwnership(h2_clone, False)
    h2_clone.SetDirectory(0)
    h2_clone.SetTitle("")
    h2_clone.SetMinimum(0.8)
    h2_clone.GetXaxis().SetRangeUser(0, x_max_plot)
    h2_clone.GetXaxis().SetLabelSize(0)
    h2_clone.GetXaxis().SetTitle("")
    h2_clone.GetYaxis().SetTitle(f"t_{{0}}^{{{ref}}} - t_{{SiPM}}^{{ToF}} [ns]")
    h2_clone.GetYaxis().SetTitleSize(0.050)
    h2_clone.GetYaxis().SetTitleOffset(1.05)
    h2_clone.GetYaxis().SetLabelSize(0.042)
    if ref == "SF":
        h2_clone.GetYaxis().SetRangeUser(-45.0, 5.0)
    else:
        h2_clone.GetYaxis().SetRangeUser(-10.0, 25.0)
    h2_clone.Draw("COLZ")

    # Total Uncertainty band (3004, kBlue+2)
    g_data_tot = ROOT.TGraphErrors(n_pts, x_arr, y_arr, dx_band, ey_tot)
    g_data_tot.SetName(f"g_data_total_error_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_data_tot, False)
    g_data_tot.SetFillColor(ROOT.kBlue + 2)
    g_data_tot.SetFillStyle(3004)
    g_data_tot.SetLineColor(ROOT.kBlue + 2)
    g_data_tot.Draw("E2 SAME")

    # Systematic Uncertainty band (3005, kTeal-5)
    g_data_syst = ROOT.TGraphErrors(n_pts, x_arr, y_arr, dx_band, sigma_syst_arr)
    g_data_syst.SetName(f"g_data_syst_error_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_data_syst, False)
    g_data_syst.SetFillColor(ROOT.kTeal - 5)
    g_data_syst.SetFillStyle(3005)
    g_data_syst.SetLineColor(ROOT.kTeal - 5)
    g_data_syst.Draw("E2 SAME")

    # Statistical SEM Data Points
    g_data_stat = ROOT.TGraphErrors(n_pts, x_arr, y_arr, np.zeros(n_pts), ey_arr)
    g_data_stat.SetName(f"g_data_stat_error_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_data_stat, False)
    g_data_stat.SetMarkerStyle(20)
    g_data_stat.SetMarkerSize(0.65)
    g_data_stat.SetMarkerColor(ROOT.kBlack)
    g_data_stat.SetLineColor(ROOT.kBlack)
    g_data_stat.Draw("PE SAME")

    # Rational Fit TF1
    fit_tf1 = ROOT.TF1(f"fit_tw_{ref}_{fixed_ch}", "[0] + [1] / ([2]*x - [3]) + [4]*x", qdc_min_fit, qdc_max_fit)
    ROOT.SetOwnership(fit_tf1, False)
    fit_tf1.SetParameters(t0, alpha, beta, qdc0, gamma)
    fit_tf1.SetLineColor(ROOT.kRed + 1)
    fit_tf1.SetLineWidth(3)
    fit_tf1.Draw("SAME")

    # Top-Left Legend
    leg = ROOT.TLegend(0.18, 0.58, 0.72, 0.92)
    ROOT.SetOwnership(leg, False)
    leg.SetBorderSize(1)
    leg.SetFillColorAlpha(ROOT.kWhite, 0.90)
    leg.SetTextFont(42)
    leg.SetTextSize(0.032)
    leg.AddEntry(g_data_stat, "Data (Statistical SEM)", "lep")
    leg.AddEntry(g_data_tot, "Total Uncertainty (SEM #oplus #sigma_{sys})", "f")
    leg.AddEntry(g_data_syst, "Systematic Floor (#sigma_{sys})", "f")
    leg.AddEntry(fit_tf1, f"Fit: #chi^{{2}}_{{stat}}/#nu = {fit_res['chi2_stat_ndf']:.1f} #rightarrow #chi^{{2}}_{{tot}}/#nu = {fit_res['chi2_tot_ndf']:.2f}", "l")
    leg.AddEntry("", f"t_{{0}} = {t0:.2f} ns, #alpha = {alpha:.2f}, #beta = {beta:.2f}", "")
    leg.AddEntry("", f"QDC_{{0}} = {qdc0:.2f}, #gamma = {gamma:.5f}", "")
    leg.AddEntry("", f"#sigma_{{sys}} = {sigma_sys*1000:.1f} ps, RMS res = {fit_res['rms_residual']*100:.2f}%", "")
    leg.Draw()

    # Title pave
    pt_title = ROOT.TPaveText(0.0, 0.96, 0.50, 1.0, "NDC")
    ROOT.SetOwnership(pt_title, False)
    pt_title.SetBorderSize(1)
    pt_title.SetFillColor(ROOT.kWhite)
    pt_title.SetTextAlign(12)
    pt_title.SetTextFont(62)
    pt_title.SetTextSize(0.038)
    run_label = f"Run {run_nr}" if run_nr > 0 else "Merged"
    pt_title.AddText(f"Channel {fixed_ch} ({ref} Ref, {run_label})")
    pt_title.Draw()

    # Bottom Pad: Data / Fit
    pad2.cd()
    denom = np.abs(y_fit)
    denom[denom == 0] = 1e-6
    ratio = y_arr / y_fit
    eratio_stat = ey_arr / denom
    eratio_syst = sigma_syst_arr / denom
    eratio_tot = ey_tot / denom

    g_ratio_tot = ROOT.TGraphErrors(n_pts, x_arr, ratio, dx_band, eratio_tot)
    g_ratio_tot.SetName(f"g_ratio_total_error_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_tot, False)
    g_ratio_tot.SetTitle(";QDC_{SiPM} [a.u.];Data / Fit")
    g_ratio_tot.SetFillColor(ROOT.kBlue + 2)
    g_ratio_tot.SetFillStyle(3004)
    g_ratio_tot.SetLineColor(ROOT.kBlue + 2)
    g_ratio_tot.GetXaxis().SetRangeUser(0, x_max_plot)
    g_ratio_tot.GetYaxis().SetRangeUser(0.92, 1.08)
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
    g_ratio_syst.SetName(f"g_ratio_syst_error_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_syst, False)
    g_ratio_syst.SetFillColor(ROOT.kTeal - 5)
    g_ratio_syst.SetFillStyle(3005)
    g_ratio_syst.SetLineColor(ROOT.kTeal - 5)
    g_ratio_syst.Draw("E2 SAME")

    # Stat markers on ratio
    g_ratio_stat = ROOT.TGraphErrors(n_pts, x_arr, ratio, np.zeros(n_pts), eratio_stat)
    g_ratio_stat.SetName(f"g_ratio_stat_error_{ref}_{fixed_ch}")
    ROOT.SetOwnership(g_ratio_stat, False)
    g_ratio_stat.SetMarkerStyle(20)
    g_ratio_stat.SetMarkerSize(0.65)
    g_ratio_stat.SetMarkerColor(ROOT.kBlack)
    g_ratio_stat.SetLineColor(ROOT.kBlack)
    g_ratio_stat.Draw("PE SAME")

    line1 = ROOT.TLine(0, 1.0, x_max_plot, 1.0)
    ROOT.SetOwnership(line1, False)
    line1.SetLineColor(ROOT.kRed + 1)
    line1.SetLineStyle(2)
    line1.SetLineWidth(2)
    line1.Draw("SAME")

    leg2 = ROOT.TLegend(0.14, 0.76, 0.60, 0.96)
    ROOT.SetOwnership(leg2, False)
    leg2.SetNColumns(3)
    leg2.SetBorderSize(0)
    leg2.SetFillStyle(0)
    leg2.SetTextFont(42)
    leg2.SetTextSize(0.065)
    leg2.AddEntry(g_ratio_tot, "Total Unc.", "f")
    leg2.AddEntry(g_ratio_syst, "Syst. Floor", "f")
    leg2.AddEntry(g_ratio_stat, "Data / Fit", "lp")
    leg2.Draw()

    c.Update()
    return c, fit_tf1, g_data_stat, g_data_tot, g_ratio_stat, g_ratio_tot


# ==============================================================================
# Global Summary Histograms & Contiguous Graph (matching fit_cscint.py)
# ==============================================================================

def build_global_timewalk_summaries(summary_tw: dict, ref: str, run_nr: int = 0):
    """
    Builds global QA distributions and contiguous alignment graph across all channels.
    US and Veto channels are placed contiguously on the x-axis without numerical gap.
    """
    ROOT.TH1.AddDirectory(False)
    channels_dict = summary_tw.get(ref, {})
    if not channels_dict:
        return {}

    hists = {}
    hists["h_chi2_ndf_tw_stat"] = ROOT.TH1F(f"h_chi2_ndf_tw_stat_{ref}", f"Time-Walk Fit #chi^{{2}}_{{stat}} / #nu ({ref});#chi^{{2}}_{{stat}} / #nu;Channels", 100, 0.0, 50.0)
    hists["h_chi2_ndf_tw_tot"] = ROOT.TH1F(f"h_chi2_ndf_tw_tot_{ref}", f"Time-Walk Fit #chi^{{2}}_{{tot}} / #nu ({ref});#chi^{{2}}_{{tot}} / #nu;Channels", 100, 0.0, 10.0)
    hists["h_sigma_sys"] = ROOT.TH1F(f"h_sigma_sys_{ref}", f"Time-Walk Systematic Floor #sigma_{{sys}} ({ref});#sigma_{{sys}} [ps];Channels", 100, 0.0, 1000.0)
    hists["h_rms_res"] = ROOT.TH1F(f"h_rms_res_{ref}", f"Time-Walk RMS Residual ({ref});RMS Residual [%];Channels", 100, 0.0, 10.0)
    hists["h_t0"] = ROOT.TH1F(f"h_tw_t0_{ref}", f"Time-Walk Offset t_{{0}} ({ref});t_{{0}} [ns];Channels", 100, -30.0, 30.0)
    hists["h_alpha"] = ROOT.TH1F(f"h_tw_alpha_{ref}", f"Time-Walk #alpha ({ref});#alpha;Channels", 100, -500.0, 0.0)
    hists["h_beta"] = ROOT.TH1F(f"h_tw_beta_{ref}", f"Time-Walk #beta ({ref});#beta;Channels", 100, 0.0, 30.0)
    hists["h_qdc0"] = ROOT.TH1F(f"h_tw_qdc0_{ref}", f"Time-Walk QDC_{{0}} ({ref});QDC_{{0}};Channels", 100, -10.0, 0.0)
    hists["h_gamma"] = ROOT.TH1F(f"h_tw_gamma_{ref}", f"Time-Walk #gamma ({ref});#gamma;Channels", 100, 0.0, 0.05)

    # Sort detector IDs and construct contiguous indexing
    parsed_channels = []
    det_ids_set = set()
    for ch_name, p in channels_dict.items():
        try:
            det, sipm = int(ch_name.split("_")[0]), int(ch_name.split("_")[1])
            det_ids_set.add(det)
            parsed_channels.append((det, sipm, ch_name, p))
        except Exception:
            continue

    det_ids = sorted(det_ids_set)
    det_to_idx = {det: i for i, det in enumerate(det_ids)}

    gr_alignment = ROOT.TGraphErrors(len(parsed_channels))
    gr_alignment.SetName(f"g_alignment_{ref}")
    gr_alignment.SetTitle(f"Fine Alignment d_{{SiPM}} ({ref});Contiguous Bar Index;d_{{SiPM}} [ns]")

    for idx, (det, sipm, ch_name, p) in enumerate(parsed_channels):
        hists["h_chi2_ndf_tw_stat"].Fill(p["chi2_stat_ndf"])
        hists["h_chi2_ndf_tw_tot"].Fill(p["chi2_tot_ndf"])
        hists["h_sigma_sys"].Fill(p["sigma_sys"] * 1000.0)
        hists["h_rms_res"].Fill(p["rms_residual"] * 100.0)
        hists["h_t0"].Fill(p["t0"])
        hists["h_alpha"].Fill(p["alpha"])
        hists["h_beta"].Fill(p["beta"])
        hists["h_qdc0"].Fill(p["qdc0"])
        hists["h_gamma"].Fill(p["gamma"])

        base_x = det_to_idx[det]
        x_coord = base_x + (sipm - 7.5) / 18.0
        d_val = p.get("alignment_d", p["t0"])
        d_unc = p.get("alignment_d_err", p["sigma_sys"])
        gr_alignment.SetPoint(idx, x_coord, d_val)
        gr_alignment.SetPointError(idx, 0.0, d_unc)

    gr_alignment.SetMarkerStyle(20)
    gr_alignment.SetMarkerSize(0.6)
    gr_alignment.SetMarkerColor(ROOT.kAzure + 2 if ref == "DS" else ROOT.kMagenta + 2)
    gr_alignment.SetLineColor(ROOT.kAzure + 2 if ref == "DS" else ROOT.kMagenta + 2)

    hists["g_alignment"] = gr_alignment
    return hists


# ==============================================================================
# File Processing Workflow
# ==============================================================================

def fit_file(
    root_path: str,
    output_path: str = None,
    cscint_file: str = None,
    cscint_dir: str = "/eos/user/i/idioniso/Timing/cscint/fits",
    save_canvas: bool = True,
    palette: str = "jet",
    qdc_min: float = 1.0,
    min_bin_entries: int = 10,
    min_total_entries: int = 200,
    verbose: bool = False
):
    """
    Fits Time-Walk rational curves for all channels in root_path.
    Saves fit canvases, TF1 functions, and ratio graphs into the ROOT file.
    Produces a consolidated calibration dictionary embedding c_scint constants.
    """
    target_path = output_path if output_path else root_path

    is_network = root_path.startswith("/eos") or target_path.startswith("/eos")
    if is_network:
        tmp_fd, work_file = tempfile.mkstemp(suffix=".root", prefix="timewalk_fit_")
        os.close(tmp_fd)
        shutil.copyfile(root_path, work_file)
    else:
        work_file = target_path
        if output_path and output_path != root_path:
            shutil.copyfile(root_path, work_file)

    mode = "UPDATE" if save_canvas else "READ"
    f = ROOT.TFile.Open(work_file, mode)
    if not f or f.IsZombie():
        print(f"[ERROR] Cannot open ROOT file: {work_file}", file=sys.stderr)
        if is_network and os.path.exists(work_file):
            os.remove(work_file)
        return None

    # Resolve run number from path (e.g. run5119.root or /run5119/part_0.root)
    import re
    m_run = re.search(r"run_?(\d+)", root_path)
    if m_run:
        run_nr = int(m_run.group(1))
    else:
        bname = os.path.basename(root_path)
        rnum_str = "".join([c for c in bname.replace(".root", "") if c.isdigit()])
        run_nr = int(rnum_str) if rnum_str else 0
    category = get_run_category(run_nr) if run_nr > 0 else "unknown"

    # Identify channel directories: can be top-level (<detID>_<sipm>) or inside cat/run hierarchy
    ch_dirs = []
    top_keys = [k.GetName() for k in f.GetListOfKeys()]

    # Case A: Top-level channel directories (standard merged run file)
    direct_ch = [k for k in top_keys if "_" in k and k.split("_")[0].isdigit()]
    if direct_ch:
        ch_dirs = [(k, f.GetDirectory(k)) for k in direct_ch]
    else:
        # Case B: Nested directory <category>/run<RUN>/<channel>
        for k in top_keys:
            cat_d = f.GetDirectory(k)
            if not cat_d:
                continue
            for rk in cat_d.GetListOfKeys():
                r_name = rk.GetName()
                if not r_name.startswith("run"):
                    continue
                r_dir = cat_d.GetDirectory(r_name)
                if not r_dir:
                    continue
                for chk in r_dir.GetListOfKeys():
                    ch_name = chk.GetName()
                    if "_" in ch_name and ch_name.split("_")[0].isdigit():
                        ch_dirs.append((ch_name, r_dir.GetDirectory(ch_name)))

    summary_tw = {"DS": {}, "SF": {}}
    summary_alignment = {"DS": {}, "SF": {}}

    total_ch = len(ch_dirs)
    if verbose:
        print(f" ~ [Run {run_nr}] Discovered {total_ch} candidate SiPM channels to fit.", flush=True)

    for idx, (ch_name, ch_dir) in enumerate(ch_dirs):
        if ch_name == "21005_15":
            continue
        try:
            detID, sipm = [int(p) for p in ch_name.split("_")]
        except ValueError:
            continue

        for ref, h_keys in [("DS", ["dtvqdc-DS", "dtvqdc_DS"]), ("SF", ["dtvqdc-SF", "dtvqdc_SF"])]:
            h2 = None
            for hk in h_keys:
                candidate = ch_dir.Get(hk)
                if candidate and candidate.InheritsFrom("TH2"):
                    h2 = candidate
                    break
            if not h2:
                continue

            fit_res = fit_single_timewalk_hist(
                h2, ref=ref, fixed_ch=ch_name, qdc_min=qdc_min,
                min_bin_entries=min_bin_entries, min_total_entries=min_total_entries
            )
            if fit_res is None:
                continue

            summary_tw[ref][ch_name] = {
                "t0": fit_res["t0"],
                "alpha": fit_res["alpha"],
                "beta": fit_res["beta"],
                "qdc0": fit_res["qdc0"],
                "gamma": fit_res["gamma"],
                "sigma_sys": fit_res["sigma_sys"],
                "chi2_stat_ndf": fit_res["chi2_stat_ndf"],
                "chi2_tot_ndf": fit_res["chi2_tot_ndf"],
                "rms_residual": fit_res["rms_residual"],
                "qdc_limits": fit_res["qdc_limits"],
                "alignment_d": fit_res["alignment_d"],
                "alignment_d_err": fit_res["alignment_d_err"],
            }
            summary_alignment[ref][ch_name] = [fit_res["alignment_d"], fit_res["alignment_d_err"]]

            if save_canvas:
                c, fit_tf1, g_stat, g_tot, gr_stat, gr_tot = build_timewalk_canvas(h2, ch_name, ref, fit_res, run_nr=run_nr, palette=palette)
                ch_dir.cd()
                ch_dir.WriteObject(c, c.GetName(), "kOverwrite")
                ch_dir.WriteObject(fit_tf1, fit_tf1.GetName(), "kOverwrite")
                ch_dir.WriteObject(g_stat, g_stat.GetName(), "kOverwrite")
                ch_dir.WriteObject(g_tot, g_tot.GetName(), "kOverwrite")
                ch_dir.WriteObject(gr_stat, gr_stat.GetName(), "kOverwrite")
                ch_dir.WriteObject(gr_tot, gr_tot.GetName(), "kOverwrite")
                h_res = fit_res["h_residual"]
                ch_dir.WriteObject(h_res, h_res.GetName(), "kOverwrite")
                c.Close()

    # Build Global Summary Directories
    if save_canvas and (summary_tw["DS"] or summary_tw["SF"]):
        sum_root_dir = f.GetDirectory("Summary")
        if not sum_root_dir:
            sum_root_dir = f.mkdir("Summary")

        for ref in ("DS", "SF"):
            ref_hists = build_global_timewalk_summaries(summary_tw, ref=ref, run_nr=run_nr)
            if not ref_hists:
                continue
            ref_dir = sum_root_dir.GetDirectory(ref)
            if not ref_dir:
                ref_dir = sum_root_dir.mkdir(ref)
            ref_dir.cd()
            for obj_name, obj in ref_hists.items():
                obj.Write(obj.GetName(), ROOT.TObject.kOverwrite)

    f.Close()

    if is_network:
        shutil.copyfile(work_file, target_path)
        os.remove(work_file)

    # Load and embed corresponding c_scint constants
    cscint_constants = {}
    cscint_candidates = []
    if cscint_file and os.path.exists(cscint_file):
        cscint_candidates.append(cscint_file)
    if cscint_dir and run_nr > 0:
        cscint_candidates.extend([
            os.path.join(cscint_dir, f"run{run_nr}_cscint.json"),
            os.path.join(cscint_dir, f"run{run_nr:06d}_cscint.json"),
            os.path.join(cscint_dir, f"run_{run_nr}_cscint.json"),
            os.path.join(cscint_dir, f"run{run_nr}.json"),
        ])

    for cand in cscint_candidates:
        if os.path.exists(cand):
            try:
                with open(cand, "r") as cjf:
                    cscint_constants = json.load(cjf)
                if verbose:
                    print(f" ~ [Run {run_nr}] Embedded c_scint constants from: {cand}", flush=True)
                break
            except Exception:
                continue

    # Summary statistics for timewalk parameters
    summary_stats = {}
    for ref in ("DS", "SF"):
        c_dict = summary_tw.get(ref, {})
        n_c = len(c_dict)
        if n_c > 0:
            summary_stats[ref] = {
                "n_channels": n_c,
                "median_t0": float(np.median([v["t0"] for v in c_dict.values()])),
                "median_alpha": float(np.median([v["alpha"] for v in c_dict.values()])),
                "median_beta": float(np.median([v["beta"] for v in c_dict.values()])),
                "median_sigma_sys": float(np.median([v["sigma_sys"] for v in c_dict.values()])),
                "mean_chi2_stat_ndf": float(np.mean([v["chi2_stat_ndf"] for v in c_dict.values()])),
                "mean_chi2_tot_ndf": float(np.mean([v["chi2_tot_ndf"] for v in c_dict.values()])),
            }
        else:
            summary_stats[ref] = {"n_channels": 0}

    out_data = {
        "run": run_nr,
        "category": category,
        "timewalk": summary_tw,
        "alignment": summary_alignment,
        "summary": summary_stats,
    }
    if cscint_constants:
        out_data["cscint"] = cscint_constants

    return out_data


# ==============================================================================
# Worker Task for Multiprocessing
# ==============================================================================

def worker_task(task_args):
    fpath, rnum, cat, out_json, out_root, cscint_dir, save_canvas, palette, qdc_min, min_bin, min_tot, verbose = task_args
    try:
        res = fit_file(
            root_path=fpath,
            output_path=out_root,
            cscint_dir=cscint_dir,
            save_canvas=save_canvas,
            palette=palette,
            qdc_min=qdc_min,
            min_bin_entries=min_bin,
            min_total_entries=min_tot,
            verbose=verbose
        )
        if res is not None:
            os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
            with open(out_json, "w") as jf:
                json.dump(res, jf, indent=2)
            n_ds = len(res["timewalk"].get("DS", {}))
            n_sf = len(res["timewalk"].get("SF", {}))
            has_cs = "cscint" in res
            return (rnum, cat, True, f"Fitted: DS={n_ds}, SF={n_sf} channels (cscint embedded: {has_cs})")
        return (rnum, cat, False, "No channels met fitting threshold")
    except Exception as e:
        return (rnum, cat, False, f"Exception: {str(e)}")


# ==============================================================================
# Main Command-Line Interface
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Extract Time-Walk calibration parameters via rational function fitting.")
    parser.add_argument("-i", "--input", type=str, help="Single input merged Time-Walk ROOT file (e.g., run5119.root)")
    parser.add_argument("-o", "--output", type=str, help="Output JSON file or directory for results")
    parser.add_argument("--input-dir", type=str, help="Directory containing merged run ROOT files (e.g., .../timewalk/runs)")
    parser.add_argument("-c", "--category", "--categories", nargs="+", default=["catII"],
                        help="Categories to process when scanning input-dir: catI, catII, catIII, or all (default: catII)")
    parser.add_argument("-j", "--jobs", type=int, default=4, help="Number of parallel worker processes (default: 4)")
    parser.add_argument("--cscint-dir", type=str, default="/eos/user/i/idioniso/Timing/cscint/fits",
                        help="Directory containing run<RUN>_cscint.json constants to embed (default: /eos/user/i/idioniso/Timing/cscint/fits)")
    parser.add_argument("--cscint-file", type=str, default=None, help="Explicit path to single c_scint JSON file")
    parser.add_argument("--no-canvas", dest="save_canvas", action="store_false", default=True,
                        help="Do not store fit canvases and TF1 in the output ROOT file")
    parser.add_argument("--palette", type=str, default="jet", choices=["jet", "plasma", "rainbow", "viridis"],
                        help="Colormap palette for 2D histograms: jet, plasma, rainbow, viridis (default: jet)")
    parser.add_argument("--output-root-dir", type=str, default=None,
                        help="Optional output directory for updated ROOT files (default: update in-place)")
    parser.add_argument("--qdc-min", type=float, default=1.0, help="Minimum QDC value to fit (default: 1.0)")
    parser.add_argument("--min-bin-entries", type=int, default=10, help="Minimum entries per QDC slice projection (default: 10)")
    parser.add_argument("--min-total-entries", type=int, default=200, help="Minimum total entries in histogram to fit (default: 200)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print verbose progress")
    args = parser.parse_args()

    if args.input:
        out_json = args.output if (args.output and args.output.endswith(".json")) else args.input.replace(".root", "_timing_calibration.json")
        out_root = args.output_root_dir
        if out_root and os.path.isdir(out_root):
            out_root = os.path.join(out_root, os.path.basename(args.input))

        res = fit_file(
            root_path=args.input,
            output_path=out_root,
            cscint_file=args.cscint_file,
            cscint_dir=args.cscint_dir,
            save_canvas=args.save_canvas,
            palette=args.palette,
            qdc_min=args.qdc_min,
            min_bin_entries=args.min_bin_entries,
            min_total_entries=args.min_total_entries,
            verbose=args.verbose
        )
        if res is not None:
            os.makedirs(os.path.dirname(os.path.abspath(out_json)), exist_ok=True)
            with open(out_json, "w") as jf:
                json.dump(res, jf, indent=2)
            n_ds = len(res["timewalk"].get("DS", {}))
            n_sf = len(res["timewalk"].get("SF", {}))
            print(f"[SUCCESS] Saved consolidated calibration constants to: {out_json}")
            print(f"  -> DS: {n_ds} channels fitted, SF: {n_sf} channels fitted.")
            if "cscint" in res:
                print(f"  -> Successfully embedded c_scint constants from JSON.")
            if args.save_canvas:
                target_written = out_root if out_root else args.input
                print(f"[SUCCESS] Saved fit canvases and summary QA distributions into ROOT file: {target_written}")

    elif args.input_dir:
        target_cats = normalize_categories(args.category)
        out_dir = args.output if args.output else os.path.join(args.input_dir, "fits")
        os.makedirs(out_dir, exist_ok=True)

        all_files = sorted(glob.glob(os.path.join(args.input_dir, "run*.root")))
        tasks = []
        for fpath in all_files:
            bname = os.path.basename(fpath)
            rnum_str = "".join([c for c in bname.replace(".root", "") if c.isdigit()])
            try:
                rnum = int(rnum_str)
            except ValueError:
                continue

            cat = get_run_category(rnum)
            if cat not in target_cats:
                continue

            out_run_json = os.path.join(out_dir, f"run{rnum}_timing_calibration.json")
            out_run_root = None
            if args.output_root_dir:
                os.makedirs(args.output_root_dir, exist_ok=True)
                out_run_root = os.path.join(args.output_root_dir, bname)

            tasks.append((
                fpath, rnum, cat, out_run_json, out_run_root, args.cscint_dir,
                args.save_canvas, args.palette, args.qdc_min, args.min_bin_entries, args.min_total_entries, args.verbose
            ))

        print("======================================================================")
        print(f" SND@LHC Time-Walk Calibration Extraction Pipeline")
        print(f" Input Directory    : {args.input_dir}")
        print(f" Target Categories  : {list(target_cats)}")
        print(f" Number of Runs     : {len(tasks)}")
        print(f" Parallel Workers   : {args.jobs}")
        print(f" c_scint Directory  : {args.cscint_dir}")
        print(f" Output JSON Dir    : {out_dir}")
        print("======================================================================")

        all_results = {}
        with multiprocessing.Pool(processes=args.jobs) as pool:
            for rnum, cat, success, msg in pool.imap_unordered(worker_task, tasks):
                status_tag = "[SUCCESS]" if success else "[WARNING]"
                print(f" {status_tag} Run {rnum:<6} ({cat}): {msg}", flush=True)
                if success:
                    all_results[rnum] = {"category": cat, "status": "fitted"}

        summary_file = os.path.join(out_dir, "all_runs_timewalk_summary.json")
        with open(summary_file, "w") as sf:
            json.dump(all_results, sf, indent=2)

        print("\n======================================================================")
        print(f"[FINISHED] All requested runs processed.")
        print(f" Summary written to: {summary_file}")
        print("======================================================================")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
