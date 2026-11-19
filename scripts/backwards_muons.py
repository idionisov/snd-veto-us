#!/usr/bin/env python3
"""
backwards_muons.py
------------------
Investigates the "Late Veto Hit" veto cut and the impact of time-walk calibration
on backwards propagating muons in SND@LHC.

Physics Goal:
  A veto cut removes events where the Veto is activated, UNLESS all veto hits are "late".
  A veto hit is "late" if it occurs at least dt_threshold (default +300 ps) after the
  earliest SciFi hit:
      delta_t = t_Veto - t_SciFi_earliest >= tau (e.g. +0.3 ns)

  The event survives (is NOT vetoed) if:
      min_{veto hits} (t_Veto - t_SciFi_earliest) >= tau

Evaluates:
  1. Particle gun simulation of backwards muons (pure truth Geant4, uncalibrated).
  2. Prefiltered 2023 data events (run 6596) under:
     - Raw DAQ times (uncalibrated)
     - Time-Walk corrected Veto times
     - Synchronized & Time-Walk calibrated times (inter-subsystem aligned)
"""

import os
import sys
import glob
import json
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator
from scipy.optimize import curve_fit

import ROOT
ROOT.gROOT.SetBatch(True)

try:
    import ddfUtils.mpl_styling as dms
    HAS_DMS = True
except ImportError:
    HAS_DMS = False

DEFAULT_SIM_FILE = "/eos/user/i/idioniso/snd-numu-charm/data/pgun_backwards_muons/sndLHC.PG_13-TGeant4_dig_b2nob1Muons.root"
DEFAULT_DATA_DIR = "/eos/user/i/idioniso/snd-numu-charm/prefiltered/2023/b2nob1Muons/run006596"
DEFAULT_CALIB_FILE = "/eos/user/i/idioniso/Timing/timewalk/fits/catII_timing_calibration.json"
DEFAULT_OUTPUT_DIR = "plots/backwards_muons"

TDC2NS = 1.0E9 / 160.316E6  # 6.237699 ns per TDC clock cycle


def gaus_func(x, a, mu, sigma):
    return a * np.exp(-0.5 * ((x - mu) / max(1e-6, sigma)) ** 2)


def fit_gaussian_core(data, bins=80, range_x=(-10.0, 10.0), n_sigma=1.8):
    """Fits Gaussian to core of distribution around the peak."""
    data = np.asarray(data)
    data = data[np.isfinite(data)]
    data = data[(data >= range_x[0]) & (data <= range_x[1])]
    if len(data) < 30:
        return None

    counts, bin_edges = np.histogram(data, bins=bins, range=range_x)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])
    max_idx = np.argmax(counts)
    peak_x = bin_centers[max_idx]
    peak_y = counts[max_idx]

    half_max = 0.5 * peak_y
    above = np.where(counts >= half_max)[0]
    if len(above) > 1:
        fwhm = bin_centers[above[-1]] - bin_centers[above[0]]
        approx_sigma = max(fwhm / 2.355, 0.2)
    else:
        approx_sigma = max(0.2, np.std(data))

    fit_mask = (bin_centers >= peak_x - n_sigma * approx_sigma) & (bin_centers <= peak_x + n_sigma * approx_sigma)
    if np.sum(fit_mask) < 4:
        fit_mask = counts > 0

    x_fit = bin_centers[fit_mask]
    y_fit = counts[fit_mask]
    ey_fit = np.sqrt(np.maximum(1.0, y_fit))

    p0 = [peak_y, peak_x, approx_sigma]
    bounds = ([0.0, range_x[0], 0.05], [peak_y * 3.0, range_x[1], 15.0])

    try:
        popt, pcov = curve_fit(gaus_func, x_fit, y_fit, p0=p0, sigma=ey_fit, bounds=bounds, maxfev=5000)
        perr = np.sqrt(np.diag(pcov))
        return {
            "amp": popt[0], "amp_err": perr[0],
            "mu": popt[1], "mu_err": perr[1],
            "sigma": abs(popt[2]), "sigma_err": perr[2],
            "fit_x_min": x_fit[0], "fit_x_max": x_fit[-1],
        }
    except Exception:
        return {
            "amp": peak_y, "amp_err": 0.0,
            "mu": float(np.median(data)), "mu_err": 0.0,
            "sigma": float(np.std(data)), "sigma_err": 0.0,
            "fit_x_min": range_x[0], "fit_x_max": range_x[1],
        }


def load_calibration(calib_file, ref="SF"):
    if not os.path.exists(calib_file):
        raise FileNotFoundError(f"Calibration file not found: {calib_file}")
    with open(calib_file, "r") as f:
        calib = json.load(f)
    tw_dict = calib.get("timewalk", {}).get(ref, {})
    align_dict = calib.get("alignment", {}).get(ref, {})
    return tw_dict, align_dict


def process_simulation(sim_file, window_min=0.0, window_max=30.0, max_events=None):
    """Processes simulation ROOT file (cbmsim tree) with uncalibrated Geant4 truth times at the bar level."""
    f = ROOT.TFile.Open(sim_file, "READ")
    if not f or f.IsZombie():
        raise RuntimeError(f"Could not open simulation file: {sim_file}")

    tree = f.Get("cbmsim")
    if not tree:
        f.Close()
        raise RuntimeError(f"cbmsim tree not found in {sim_file}")

    n_entries = tree.GetEntries()
    if max_events and max_events < n_entries:
        n_entries = max_events

    results = []
    for i in range(n_entries):
        tree.GetEntry(i)

        sf_times = []
        for h in tree.Digi_ScifiHits:
            if h.isValid():
                t_ns = h.GetTime()
                if window_min <= t_ns <= window_max:
                    sf_times.append(t_ns)

        if not sf_times:
            continue
        t_sf_earliest = min(sf_times)

        veto_bar_times = []
        for h in tree.Digi_MuFilterHits:
            detID = h.GetDetectorID()
            if detID // 10000 == 1:
                s0, s1 = [], []
                for p in h.GetAllTimes():
                    sipm = p.first
                    t_ns = p.second
                    if window_min <= t_ns <= window_max:
                        if sipm < 8:
                            s0.append(t_ns)
                        else:
                            s1.append(t_ns)

                is_vert = h.isVertical()
                if is_vert:
                    if s0:
                        veto_bar_times.append(np.mean(s0))
                else:
                    if s0 and s1:
                        veto_bar_times.append(0.5 * (np.mean(s0) + np.mean(s1)))
                    elif s0:
                        veto_bar_times.append(np.mean(s0))
                    elif s1:
                        veto_bar_times.append(np.mean(s1))

        if veto_bar_times:
            diffs = [t_v - t_sf_earliest for t_v in veto_bar_times]
            results.append({
                "t_sf_earliest": t_sf_earliest,
                "t_veto_min": min(veto_bar_times),
                "t_veto_max": max(veto_bar_times),
                "dt_min": min(diffs),  # Worst-case bar for late-veto cut
                "dt_max": max(diffs),  # Latest bar for late-veto cut
                "n_veto_bars": len(diffs),
            })

    f.Close()
    return pd.DataFrame(results)


def process_single_data_file(args):
    """Worker function to process a single data ROOT file."""
    file_path, tw_dict, align_dict, window_min, window_max, max_events = args
    results = []

    f = ROOT.TFile.Open(file_path, "READ")
    if not f or f.IsZombie():
        return results

    tree = f.Get("rawConv")
    if not tree:
        f.Close()
        return results

    n_entries = tree.GetEntries()
    if max_events and max_events < n_entries:
        n_entries = max_events

    for i in range(n_entries):
        tree.GetEntry(i)

        sf_times = []
        for h in tree.Digi_ScifiHits:
            if h.isValid():
                t_ns = h.GetTime() * TDC2NS
                if window_min <= t_ns <= window_max:
                    sf_times.append(t_ns)

        if not sf_times:
            continue
        t_sf_earliest = min(sf_times)

        bar_raw = []
        bar_tw = []
        bar_calib = []

        for h in tree.Digi_MuFilterHits:
            detID = h.GetDetectorID()
            if detID // 10000 == 1:  # Veto
                qdc_dict = {p.first: p.second for p in h.GetAllSignals()}
                s0_raw, s1_raw = [], []
                s0_tw, s1_tw = [], []
                s0_cal, s1_cal = [], []

                for p in h.GetAllTimes():
                    sipm = p.first
                    t_ns = p.second * TDC2NS
                    if not (window_min <= t_ns <= window_max):
                        continue
                    qdc = qdc_dict.get(sipm, -1.0)
                    ch_key = f"{detID}_{sipm}"

                    # Clamped time-walk correction
                    if ch_key in tw_dict:
                        par = tw_dict[ch_key]
                        q_clamped = max(2.0, min(100.0, qdc))
                        denom = max(1e-4, par["beta"] * q_clamped - par["qdc0"])
                        tw = par["alpha"] / denom + par["gamma"] * q_clamped
                        tw = max(-5.0, min(2.0, tw))
                        t_tw = t_ns + tw

                        d_val = align_dict[ch_key][0] if ch_key in align_dict else 0.0
                        t_cal = t_tw + d_val
                    else:
                        t_tw = t_ns
                        t_cal = t_ns

                    if sipm < 8:
                        s0_raw.append(t_ns)
                        s0_tw.append(t_tw)
                        s0_cal.append(t_cal)
                    else:
                        s1_raw.append(t_ns)
                        s1_tw.append(t_tw)
                        s1_cal.append(t_cal)

                is_vert = h.isVertical()
                if is_vert:
                    if s0_raw:
                        bar_raw.append(np.mean(s0_raw))
                        bar_tw.append(np.mean(s0_tw))
                        bar_calib.append(np.mean(s0_cal))
                else:
                    if s0_raw and s1_raw:
                        bar_raw.append(0.5 * (np.mean(s0_raw) + np.mean(s1_raw)))
                        bar_tw.append(0.5 * (np.mean(s0_tw) + np.mean(s1_tw)))
                        bar_calib.append(0.5 * (np.mean(s0_cal) + np.mean(s1_cal)))
                    elif s0_raw:
                        bar_raw.append(np.mean(s0_raw))
                        bar_tw.append(np.mean(s0_tw))
                        bar_calib.append(np.mean(s0_cal))
                    elif s1_raw:
                        bar_raw.append(np.mean(s1_raw))
                        bar_tw.append(np.mean(s1_tw))
                        bar_calib.append(np.mean(s1_cal))

        if bar_raw:
            d_raw = [t - t_sf_earliest for t in bar_raw]
            d_tw = [t - t_sf_earliest for t in bar_tw]
            d_cal = [t - t_sf_earliest for t in bar_calib]
            results.append({
                "raw_min_dt": min(d_raw),
                "raw_max_dt": max(d_raw),
                "tw_min_dt": min(d_tw),
                "tw_max_dt": max(d_tw),
                "cal_min_dt": min(d_cal),
                "cal_max_dt": max(d_cal),
                "n_veto_bars": len(d_raw),
            })

    f.Close()
    return results


def plot_late_veto_analysis(df_sim, df_data, out_dir, tau_cut=0.3, df_nu=None):
    """
    Plots comprehensive late-veto cut investigation:
      (a) Simulation dt distribution (PGun Backwards mu vs Genie nu Backsplash)
      (b) Data dt distribution (Raw vs TW-corrected)
      (c) Late-veto cut survival efficiency vs threshold tau
      (d) Synchronized Data vs Simulation comparison
    """
    fig, axes = plt.subplots(2, 2, figsize=(15.5, 11.2))
    (ax1, ax2), (ax3, ax4) = axes

    # --- Panel 1: Simulation (MC Truth) ---
    bins_sim = np.linspace(-2.0, 9.0, 111)
    ax1.hist(df_sim["dt_min"], bins=bins_sim, histtype="stepfilled", color="#64B5F6", alpha=0.5,
             label=rf"PGun Backwards $\mu$ Min $\Delta t$ (med: {np.median(df_sim['dt_min']):+.2f} ns)")
    ax1.hist(df_sim["dt_min"], bins=bins_sim, histtype="step", color="#1976D2", linewidth=2.0)
    ax1.hist(df_sim["dt_max"], bins=bins_sim, histtype="step", color="#0D47A1", linewidth=1.8, linestyle="--",
             label=rf"PGun Backwards $\mu$ Max $\Delta t$ (med: {np.median(df_sim['dt_max']):+.2f} ns)")

    if df_nu is not None and len(df_nu) > 0:
        ax1.hist(df_nu["dt_min"], bins=bins_sim, histtype="step", color="#7B1FA2", linewidth=2.2, linestyle="-.",
                 label=rf"Genie $\nu$ Backsplash Min $\Delta t$ (med: {np.median(df_nu['dt_min']):+.2f} ns)")

    ax1.axvline(tau_cut, color="#D32F2F", linestyle=":", linewidth=2.5,
                label=rf"Cut Threshold $\tau = {int(tau_cut*1000)}$ ps")

    pass_sim_300 = np.mean(df_sim["dt_min"] >= tau_cut) * 100.0
    pass_nu_300 = np.mean(df_nu["dt_min"] >= tau_cut) * 100.0 if df_nu is not None else None

    tbox1 = (
        f"Backwards Survival Efficiency:\n"
        rf"  PGun $\mu$ ($\tau={int(tau_cut*1000)}$ ps): {pass_sim_300:.1f}%"
    )
    if pass_nu_300 is not None:
        tbox1 += f"\n  Genie $\\nu$ ($\tau={int(tau_cut*1000)}$ ps): {pass_nu_300:.1f}%"

    ax1.text(0.97, 0.62, tbox1,
             transform=ax1.transAxes, ha="right", va="top",
             fontsize=10.5, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#E3F2FD", edgecolor="#1976D2"))

    ax1.set_xlabel(r"$\Delta t = t_{\mathrm{Veto\,Bar}} - t_{\mathrm{SciFi}}^{\mathrm{earliest}}$ [ns]", fontsize=12)
    ax1.set_ylabel(f"Events / {bins_sim[1]-bins_sim[0]:.2f} ns", fontsize=12)
    ax1.set_xlim(-1.5, 8.5)
    ax1.xaxis.set_minor_locator(AutoMinorLocator())
    ax1.yaxis.set_minor_locator(AutoMinorLocator())
    ax1.grid(True, linestyle=":", alpha=0.5)
    ax1.legend(frameon=True, facecolor="white", edgecolor="#BDBDBD", loc="upper right", fontsize=9.0)
    if HAS_DMS:
        dms.add_label(ax=ax1, mainText="SND@LHC", extraText="Simulation", suppText="MC Truth (Bar Timing)")
    else:
        ax1.set_title("(a) Simulation (MC Truth): Late Veto Bars", fontsize=13, loc="left")

    # --- Panel 2: Real Data (Raw DAQ vs. Calibrated) ---
    bins_data = np.linspace(-9.0, 5.0, 85)
    ax2.hist(df_data["raw_min_dt"], bins=bins_data, histtype="stepfilled", color="#CFD8DC", alpha=0.5,
             label=rf"Raw DAQ Min $\Delta t_{{\mathrm{{bar}}}}$ (med: {np.median(df_data['raw_min_dt']):+.2f} ns)")
    ax2.hist(df_data["raw_min_dt"], bins=bins_data, histtype="step", color="#546E7A", linewidth=1.6)

    ax2.hist(df_data["cal_min_dt"], bins=bins_data, histtype="stepfilled", color="#FFE0B2", alpha=0.5,
             label=rf"Calibrated (TW+Align) Min $\Delta t_{{\mathrm{{bar}}}}$ (med: {np.median(df_data['cal_min_dt']):+.2f} ns)")
    ax2.hist(df_data["cal_min_dt"], bins=bins_data, histtype="step", color="#FB8C00", linewidth=2.0)

    ax2.axvline(tau_cut, color="#D32F2F", linestyle=":", linewidth=2.5,
                label=rf"Cut Threshold $\tau = {int(tau_cut*1000)}$ ps")

    raw_pass = np.mean(df_data["raw_min_dt"] >= tau_cut) * 100.0
    cal_pass = np.mean(df_data["cal_min_dt"] >= tau_cut) * 100.0

    tbox2 = (
        "Direct Unsynchronized Pass Rate:\n"
        f"Raw DAQ: $\\epsilon = {raw_pass:.1f}\\%$\n"
        f"Calibrated: $\\epsilon = {cal_pass:.1f}\\%$\n"
        f"(Offset by DAQ delay $\\sim 6.5$ ns)"
    )
    ax2.text(0.04, 0.65, tbox2,
             transform=ax2.transAxes, ha="left", va="top",
             fontsize=10.5, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.5", facecolor="#FFF3E0", edgecolor="#FB8C00"))

    ax2.set_xlabel(r"$\Delta t = t_{\mathrm{Veto\,Bar}} - t_{\mathrm{SciFi}}^{\mathrm{earliest}}$ [ns]", fontsize=12)
    ax2.set_ylabel(f"Events / {bins_data[1]-bins_data[0]:.2f} ns", fontsize=12)
    ax2.set_xlim(-9.0, 4.0)
    ax2.xaxis.set_minor_locator(AutoMinorLocator())
    ax2.yaxis.set_minor_locator(AutoMinorLocator())
    ax2.grid(True, linestyle=":", alpha=0.5)
    ax2.legend(frameon=True, facecolor="white", edgecolor="#BDBDBD", loc="upper right", fontsize=9.2)
    if HAS_DMS:
        dms.add_label(ax=ax2, mainText="SND@LHC", extraText="Data 2023", suppText="Run 6596 (Bar Timing)")
    else:
        ax2.set_title("(b) Real Detector Data: Unsynchronized DAQ Clocks", fontsize=13, loc="left")

    # --- Panel 3: Survival Efficiency vs. Threshold Tau ---
    taus = np.linspace(-3.0, 4.0, 141)
    eff_sim = [np.mean(df_sim["dt_min"] >= t) * 100.0 for t in taus]
    eff_nu = [np.mean(df_nu["dt_min"] >= t) * 100.0 for t in taus] if df_nu is not None else None
    eff_data_raw = [np.mean(df_data["raw_min_dt"] >= t) * 100.0 for t in taus]

    # Global time alignment to match physical simulation median:
    offset_raw = np.median(df_sim["dt_min"]) - np.median(df_data["raw_min_dt"])
    offset_cal = np.median(df_sim["dt_min"]) - np.median(df_data["cal_min_dt"])

    aligned_data_raw = df_data["raw_min_dt"] + offset_raw
    aligned_data_cal = df_data["cal_min_dt"] + offset_cal

    eff_data_synch_raw = [np.mean(aligned_data_raw >= t) * 100.0 for t in taus]
    eff_data_synch_cal = [np.mean(aligned_data_cal >= t) * 100.0 for t in taus]

    ax3.plot(taus * 1000.0, eff_sim, color="#1565C0", linewidth=2.5, label="PGun Backwards $\mu$ (MC Truth)")
    if eff_nu is not None:
        ax3.plot(taus * 1000.0, eff_nu, color="#7B1FA2", linewidth=2.2, linestyle="-.", label="Genie $\nu$ Backsplash (MC Truth)")
    ax3.plot(taus * 1000.0, eff_data_synch_cal, color="#C62828", linewidth=2.3, label="Data (Synchronized + Calibrated)")
    ax3.plot(taus * 1000.0, eff_data_synch_raw, color="#757575", linewidth=1.8, linestyle="--", label="Data (Synchronized, No TW)")
    ax3.plot(taus * 1000.0, eff_data_raw, color="#BDBDBD", linewidth=1.5, linestyle=":", label="Data (Raw DAQ, Unsynchronized)")

    ax3.axvline(tau_cut * 1000.0, color="#D32F2F", linestyle=":", linewidth=2.2, label=rf"Cut $\tau = {int(tau_cut*1000)}$ ps")
    ax3.set_xlabel(r"Late Veto Cut Threshold $\tau$ [ps]", fontsize=12)
    ax3.set_ylabel(r"Backwards Muon Survival Efficiency $\epsilon(\tau)$ [%]", fontsize=12)
    ax3.set_xlim(-1500, 3000)
    ax3.set_ylim(-2.0, 105.0)
    ax3.xaxis.set_minor_locator(AutoMinorLocator())
    ax3.yaxis.set_minor_locator(AutoMinorLocator())
    ax3.grid(True, linestyle=":", alpha=0.5)
    ax3.legend(frameon=True, facecolor="white", edgecolor="#BDBDBD", loc="lower left", fontsize=8.8)

    eff_synch_cal_300 = np.mean(aligned_data_cal >= tau_cut) * 100.0
    eff_synch_raw_300 = np.mean(aligned_data_raw >= tau_cut) * 100.0

    tbox3 = (
        rf"Efficiency at $\tau = 300$ ps:" + "\n"
        rf"  PGun $\mu$ : {pass_sim_300:.1f}%" + "\n"
    )
    if pass_nu_300 is not None:
        tbox3 += rf"  Genie $\nu$ : {pass_nu_300:.1f}%" + "\n"
    tbox3 += (
        rf"  Data (Cal): {eff_synch_cal_300:.1f}%" + "\n"
        rf"  Data (Raw): {eff_synch_raw_300:.1f}%"
    )

    ax3.text(0.97, 0.88, tbox3,
             transform=ax3.transAxes, ha="right", va="top",
             fontsize=10.0, fontweight="bold",
             bbox=dict(boxstyle="round,pad=0.4", facecolor="#FAFAFA", edgecolor="#BDBDBD"))

    if HAS_DMS:
        dms.add_label(ax=ax3, mainText="SND@LHC", extraText="Efficiency", suppText="Cut Threshold Scan")
    else:
        ax3.set_title("(c) Backwards Muon Survival Efficiency Scan", fontsize=13, loc="left")

    # --- Panel 4: Synchronized Comparison (Data vs Simulation) ---
    bins_comp = np.linspace(-2.0, 7.0, 91)
    ax4.hist(df_sim["dt_min"], bins=bins_comp, density=True, histtype="step", color="#1565C0", linewidth=2.5,
             label=f"PGun Backwards $\mu$ (N={len(df_sim):,})")
    if df_nu is not None and len(df_nu) > 0:
        ax4.hist(df_nu["dt_min"], bins=bins_comp, density=True, histtype="step", color="#7B1FA2", linewidth=2.0, linestyle="-.",
                 label=f"Genie $\nu$ Backsplash (N={len(df_nu):,})")
    ax4.hist(aligned_data_cal, bins=bins_comp, density=True, histtype="step", color="#C62828", linewidth=2.2,
             label=f"Data Synchronized + Calibrated (N={len(df_data):,})")
    ax4.hist(aligned_data_raw, bins=bins_comp, density=True, histtype="step", color="#9E9E9E", linewidth=1.6, linestyle="--",
             label="Data Synchronized Raw (No TW)")

    ax4.axvline(tau_cut, color="#D32F2F", linestyle=":", linewidth=2.5,
                label=rf"Cut $\tau = {int(tau_cut*1000)}$ ps")
    ax4.set_xlabel(r"Synchronized $\Delta t = t_{\mathrm{Veto\,Bar}} - t_{\mathrm{SciFi}}^{\mathrm{earliest}}$ [ns]", fontsize=12)
    ax4.set_ylabel("Normalized Probability Density", fontsize=12)
    ax4.set_xlim(-1.5, 5.5)
    ax4.xaxis.set_minor_locator(AutoMinorLocator())
    ax4.yaxis.set_minor_locator(AutoMinorLocator())
    ax4.grid(True, linestyle=":", alpha=0.5)
    ax4.legend(frameon=True, facecolor="white", edgecolor="#BDBDBD", loc="upper right", fontsize=9.2)

    fit_sim = fit_gaussian_core(df_sim["dt_min"], bins=80, range_x=(-2.0, 6.0))
    fit_dat = fit_gaussian_core(aligned_data_cal, bins=80, range_x=(-2.0, 6.0))
    if fit_sim and fit_dat:
        tbox4 = (
            "Core Gaussian Spread $\\sigma$:\n"
            f"  Sim: $\\sigma = {fit_sim['sigma']:.2f}$ ns\n"
            f"  Data (Cal): $\\sigma = {fit_dat['sigma']:.2f}$ ns"
        )
        ax4.text(0.04, 0.70, tbox4,
                 transform=ax4.transAxes, ha="left", va="top",
                 fontsize=10.5, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.4", facecolor="#EFEBE9", edgecolor="#8D6E63"))

    if HAS_DMS:
        dms.add_label(ax=ax4, mainText="SND@LHC", extraText="Synchronized", suppText="Data vs. MC (Bar Timing)")
    else:
        ax4.set_title("(d) Synchronized Physical Time-of-Flight Overlay", fontsize=13, loc="left")

    fig.tight_layout()
    out_png = os.path.join(out_dir, "backwards_muons_late_veto_analysis.png")
    out_pdf = os.path.join(out_dir, "backwards_muons_late_veto_analysis.pdf")
    fig.savefig(out_png, dpi=300)
    fig.savefig(out_pdf)
    plt.close(fig)

    return {
        "pass_sim_300": pass_sim_300,
        "pass_data_raw_300": raw_pass,
        "pass_data_cal_300": cal_pass,
        "pass_data_synch_raw_300": eff_synch_raw_300,
        "pass_data_synch_cal_300": eff_synch_cal_300,
        "offset_raw_ns": offset_raw,
        "offset_cal_ns": offset_cal,
    }


def main():
    parser = argparse.ArgumentParser(description="Investigate Late Veto Hit cut and timewalk calibration on backwards muons.")
    parser.add_argument("--sim-file", default=DEFAULT_SIM_FILE, help="Path to backwards muon simulation ROOT file.")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Path to prefiltered 2023 data directory.")
    parser.add_argument("--calib-file", default=DEFAULT_CALIB_FILE, help="Path to timing calibration JSON file.")
    parser.add_argument("--ref", default="SF", choices=["SF", "DS"], help="Reference system (SF or DS).")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for plots and metrics.")
    parser.add_argument("--max-data-files", type=int, default=50, help="Maximum number of data files to process.")
    parser.add_argument("--max-events-per-file", type=int, default=None, help="Max events per file to process.")
    parser.add_argument("--n-workers", type=int, default=8, help="Number of worker processes.")
    parser.add_argument("--tau-cut", type=float, default=0.3, help="Late veto threshold tau in ns (default 0.3 = 300 ps).")
    parser.add_argument("--window-min", type=float, default=0.0, help="Minimum physical hit time in ns.")
    parser.add_argument("--window-max", type=float, default=30.0, help="Maximum physical hit time in ns.")

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    print("=" * 78)
    print("SND@LHC Late Veto Cut & Time-Walk Investigation (Backwards Muons)")
    print("=" * 78)
    print(f"Simulation File : {args.sim_file}")
    print(f"Data Directory  : {args.data_dir}")
    print(f"Calibration File: {args.calib_file} (Reference: {args.ref})")
    print(f"Late Threshold  : {args.tau_cut * 1000.0:.0f} ps")
    print(f"Output Directory: {args.output_dir}")
    print("-" * 78)

    # 1. Load Calibration
    print("[1/4] Loading calibration constants...")
    tw_dict, align_dict = load_calibration(args.calib_file, ref=args.ref)
    print(f"      Loaded {len(tw_dict)} timewalk channels.")

    # 2. Process Simulation (Raw MC Truth only)
    print("[2/4] Processing simulation events (MC Truth)...")
    df_sim = process_simulation(
        args.sim_file,
        window_min=args.window_min, window_max=args.window_max,
        max_events=args.max_events_per_file
    )
    print(f"      Simulation: {len(df_sim):,} valid events extracted.")

    # 3. Process Data Files
    cache_path = os.path.join(args.output_dir, f"data_cache_bar_{args.ref}_{args.max_data_files}.parquet")
    if os.path.exists(cache_path):
        print(f"[3/4] Loading cached data from {cache_path}...")
        df_data = pd.read_parquet(cache_path)
        print(f"      Data: {len(df_data):,} valid events loaded from cache.")
    else:
        data_files = sorted(glob.glob(os.path.join(args.data_dir, "sndsw_raw-*.root")))
        if not data_files:
            raise FileNotFoundError(f"No sndsw_raw-*.root files found in {args.data_dir}")

        if args.max_data_files:
            data_files = data_files[:args.max_data_files]

        print(f"[3/4] Processing {len(data_files)} data files across {args.n_workers} worker processes...")
        tasks = [
            (fpath, tw_dict, align_dict, args.window_min, args.window_max, args.max_events_per_file)
            for fpath in data_files
        ]

        all_data_records = []
        with ProcessPoolExecutor(max_workers=args.n_workers) as executor:
            futures = {executor.submit(process_single_data_file, task): task[0] for task in tasks}
            for future in as_completed(futures):
                fpath = futures[future]
                try:
                    res = future.result()
                    all_data_records.extend(res)
                except Exception as e:
                    print(f"      [WARNING] Error processing {os.path.basename(fpath)}: {e}", file=sys.stderr)

        df_data = pd.DataFrame(all_data_records)
        df_data.to_parquet(cache_path)
        print(f"      Data: {len(df_data):,} valid events extracted and cached to {cache_path}.")

    # Load Neutrino Simulation if available
    nu_cache_path = os.path.join(args.output_dir, "nu_sim_cache_bar.parquet")
    df_nu = None
    if os.path.exists(nu_cache_path):
        df_nu = pd.read_parquet(nu_cache_path)
        print(f"      Neutrino Simulation: {len(df_nu):,} valid backsplash events loaded from {nu_cache_path}.")

    # 4. Generate Analysis Plots & Threshold Scans
    print("[4/4] Generating Late Veto Cut investigation figures...")
    summary = plot_late_veto_analysis(df_sim, df_data, args.output_dir, tau_cut=args.tau_cut, df_nu=df_nu)

    # 5. Save results
    json_path = os.path.join(args.output_dir, "late_veto_cut_results.json")
    with open(json_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("=" * 78)
    print(f"LATE VETO CUT RESULTS SUMMARY (Threshold tau = {int(args.tau_cut*1000)} ps):")
    print("-" * 78)
    print(f"1. Simulation (MC Truth) Survival Efficiency    : {summary['pass_sim_300']:.1f}%")
    print(f"2. Data (Raw DAQ, Unsynchronized) Pass Rate      : {summary['pass_data_raw_300']:.1f}%  <-- Fails due to DAQ clock offset!")
    print(f"3. Data (Calibrated, Unsynchronized) Pass Rate   : {summary['pass_data_cal_300']:.1f}%")
    print(f"4. Data (Synchronized, No TW) Pass Rate          : {summary['pass_data_synch_raw_300']:.1f}%")
    print(f"5. Data (Synchronized + Calibrated) Pass Rate    : {summary['pass_data_synch_cal_300']:.1f}%")
    print(f"   --> Hardware DAQ Inter-system Offset required : {summary['offset_cal_ns']:+.2f} ns")
    print(f"Figures saved to: {args.output_dir}/backwards_muons_late_veto_analysis.png")
    print("=" * 78)


if __name__ == "__main__":
    main()
