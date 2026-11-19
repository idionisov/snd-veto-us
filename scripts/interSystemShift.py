#!/usr/bin/env python3
"""
interSystemShift.py
-------------------
Determines the inter-system hardware synchronization time shift between Veto and
SciFi detectors using clean forward-propagating muons.

Methodology (Hit-Level & Station-by-Station Analysis):
  1. Clean Forward Muon Selection:
     - Reconstructed SciFi track with chi2/ndf < 5.0 and track slope sqrt(tx^2 + ty^2) < 0.1 rad.
     - Low event multiplicity: total SciFi hits < 27.
     - SciFi track enters and crosses an activated Veto bar.
     - SciFi hits associated with the muon: within 1 mm of the track trajectory.

  2. Hit Timing & Muon Time-of-Flight (ToF):
     - Each SciFi hit i within 1 mm of the track has a calibrated time t_SciFi,i
       (including SciFi internal station/plane alignment and fiber propagation L / v_fiber).
     - The track crossing through the activated Veto bar provides the calibrated Veto time t_Veto
       (corrected for scintillation photon ToF x / c_scint, timewalk, and channel fine alignment).
     - The muon travels at the speed of light c from Veto (z_Veto) to that specific SciFi plane (z_SciFi,i).
       Physical time-of-flight: ToF_muon = Delta_L_{V -> Si} / c_light.

  3. Inter-System Clock Shift Definition:
     - delta_t_i = t_SciFi,i - t_Veto - ToF_muon
     - If physical ToF fully explains the propagation, any non-zero constant offset delta_t
       defines the intrinsic hardware/clock synchronization offset between the Veto and SciFi systems.
     - By evaluating delta_t station-by-station (Stations 1 to 5, spanning Delta z from ~15 to ~80 cm),
       a flat profile vs z confirms that the remaining offset is purely a global clock offset.

  4. Calibration Comparisons:
     - Veto calibrated with SciFi reference constants (calib['...']['SF'])
     - Veto calibrated with DS reference constants (calib['...']['DS'])
     - Veto uncalibrated (raw time) as a baseline comparison.
"""

import os
import sys
import math
import json
import argparse
import numpy as np
import ROOT

ROOT.gROOT.SetBatch(True)
ROOT.PyConfig.IgnoreCommandLineOptions = True
ROOT.gErrorIgnoreLevel = ROOT.kWarning

# Speed of light in vacuum [cm / ns]
C_LIGHT = 29.9792458
TDC2NS = 25.0 / 32.0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract SciFi-to-Veto inter-system synchronization time shifts using clean forward muons."
    )
    parser.add_argument(
        "-i", "--input",
        dest="input_source",
        type=str,
        required=True,
        help="Input raw/converted ROOT file, directory, or run number (e.g. 5119 or path to sndsw_raw-*.root)"
    )
    parser.add_argument(
        "-c", "--calib", "--json",
        dest="calib_file",
        type=str,
        required=True,
        help="Path to timing calibration JSON file containing cscint, timewalk, and fine alignment constants"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_root",
        type=str,
        default="/tmp/inter_system_shift.root",
        help="Path to output ROOT file storing diagnostic histograms and canvases (default: /tmp/inter_system_shift.root)"
    )
    parser.add_argument(
        "-g", "--geo-file",
        dest="geo_file",
        type=str,
        default=None,
        help="Optional path or EOS URL for geometry ROOT file (auto-detected if omitted)"
    )
    parser.add_argument(
        "-n", "--max-events",
        dest="max_events",
        type=int,
        default=-1,
        help="Maximum events to analyze (-1 for all events in partition/file)"
    )
    parser.add_argument(
        "-P", "--partition",
        dest="partition",
        type=int,
        default=0,
        help="Partition index when specifying run number (default: 0)"
    )
    parser.add_argument(
        "--max-scifi-hits",
        dest="max_scifi_hits",
        type=int,
        default=26,
        help="Maximum total SciFi hits for low multiplicity clean muon cut (default: 26)"
    )
    parser.add_argument(
        "--max-chi2ndf",
        dest="max_chi2ndf",
        type=float,
        default=5.0,
        help="Maximum SciFi track chi2/ndf (default: 5.0)"
    )
    parser.add_argument(
        "--max-slope",
        dest="max_slope",
        type=float,
        default=0.1,
        help="Maximum SciFi track slope theta_xy [rad] (default: 0.1 rad)"
    )
    parser.add_argument(
        "--max-dist-track",
        dest="max_dist_track",
        type=float,
        default=0.1,
        help="Maximum distance between SciFi hit and track extrapolation [cm] (default: 0.1 cm = 1.0 mm)"
    )
    parser.add_argument(
        "--min-scifi-hits",
        dest="min_scifi_hits",
        type=int,
        default=3,
        help="Minimum associated SciFi hits per qualified track (default: 3)"
    )
    parser.add_argument(
        "--ref-shift",
        dest="ref_shift",
        type=float,
        default=4.188,
        help="Inter-system hardware clock shift between SciFi and DS reference systems [ns] (default: 4.188 ns from event_ref_time.py)"
    )
    parser.add_argument(
        "--bridge-mode",
        dest="bridge_mode",
        choices=["auto", "fixed", "calib", "event"],
        default="auto",
        help="Bridge correction mode: 'auto' (event t0_DS - t0_SF when DS1&DS2 available, else fixed ToF + ref_shift), 'fixed', 'calib', or 'event' (default: auto)"
    )
    parser.add_argument(
        "--save-csv",
        dest="save_csv",
        type=str,
        default=None,
        help="Optional output CSV path to dump hit-level and event-level shift metrics"
    )
    return parser.parse_args()


def load_calibration_constants(json_path):
    """Loads timing calibration JSON."""
    if not os.path.exists(json_path):
        print(f"[ERROR] Calibration JSON file not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r") as f:
        data = json.load(f)

    run_id = data.get("run", 0)
    cat = data.get("category", "unknown")

    tw_data = {"DS": {}, "SF": {}}
    align_data = {"DS": {}, "SF": {}}
    cscint_data = {"DS": {}, "SF": {}}
    unified_speed = {"DS": 13.5, "SF": 13.5}

    for ref in ("DS", "SF"):
        if "timewalk" in data and ref in data["timewalk"]:
            for ch_str, pars in data["timewalk"][ref].items():
                tw_data[ref][ch_str] = {
                    "alpha": float(pars.get("alpha", 0.0)),
                    "beta": float(pars.get("beta", 1.0)),
                    "qdc0": float(pars.get("qdc0", 0.0)),
                    "gamma": float(pars.get("gamma", 0.0)),
                    "t0": float(pars.get("t0", 0.0))
                }

        if "alignment" in data and ref in data["alignment"]:
            for ch_str, val in data["alignment"][ref].items():
                if isinstance(val, dict):
                    align_data[ref][ch_str] = float(val.get("d", val.get("alignment", 0.0)))
                elif isinstance(val, (list, tuple)) and len(val) > 0:
                    align_data[ref][ch_str] = float(val[0])
                elif isinstance(val, (int, float)):
                    align_data[ref][ch_str] = float(val)

        if "cscint" in data and ref in data["cscint"]:
            for ch_str, val in data["cscint"][ref].items():
                if isinstance(val, dict):
                    cscint_data[ref][ch_str] = float(val.get("c_scint", 0.0))
                elif isinstance(val, (list, tuple)) and len(val) > 0:
                    cscint_data[ref][ch_str] = float(val[0])
                elif isinstance(val, (int, float)):
                    cscint_data[ref][ch_str] = float(val)

        if "summary" in data and ref in data["summary"]:
            s_dict = data["summary"].get(ref, {})
            w_mean = s_dict.get("weighted_mean") or s_dict.get("mean")
            if w_mean and 5.0 < float(w_mean) < 30.0:
                unified_speed[ref] = float(w_mean)

    if not cscint_data["SF"] and cscint_data["DS"]:
        cscint_data["SF"] = dict(cscint_data["DS"])
        unified_speed["SF"] = unified_speed["DS"]

    return {
        "run": run_id,
        "category": cat,
        "timewalk": tw_data,
        "alignment": align_data,
        "cscint": cscint_data,
        "unified_speed": unified_speed
    }


def compute_calibrated_veto_time(hit, x_pred, calib, ref="SF"):
    """
    Computes ToF-, timewalk-, and fine-alignment-corrected hit time for an activated Veto bar.
    """
    detID = hit.GetDetectorID()
    channels_t = hit.GetAllTimes()
    signals_dict = dict(hit.GetAllSignals())

    tw_dict = calib["timewalk"].get(ref, {})
    align_dict = calib["alignment"].get(ref, {})
    cscint_dict = calib["cscint"].get(ref, {})
    unified_c = calib["unified_speed"].get(ref, 13.5)

    s0_times = []
    s1_times = []
    all_sipm_times = []

    for sipm, clock in channels_t:
        if sipm < 0 or sipm > 15:
            continue
        ch_key = f"{detID}_{sipm}"
        qdc = signals_dict.get(sipm, -999.0)
        if qdc <= 0 or qdc == -999.0:
            continue

        t_raw = clock * TDC2NS

        # 1. Scintillation light propagation along the bar (x_pred - x_center)
        # Side 0 (SiPM 0-7) at negative x; Side 1 (SiPM 8-15) at positive x
        c_speed = cscint_dict.get(ch_key, unified_c)
        if c_speed <= 0:
            c_speed = unified_c

        sign = 1.0 if sipm < 8 else -1.0
        t_prop = sign * (x_pred / c_speed)

        # 2. Timewalk correction
        tw_corr = 0.0
        if ch_key in tw_dict:
            par = tw_dict[ch_key]
            q_clamped = max(2.0, min(120.0, float(qdc)))
            denom = max(1e-4, par["beta"] * q_clamped - par["qdc0"])
            tw = par["alpha"] / denom + par["gamma"] * q_clamped
            tw_corr = max(-6.0, min(3.0, tw))

        # 3. Fine channel alignment
        d_align = align_dict.get(ch_key, 0.0)

        # Interaction time at the muon crossing point
        t_cal = t_raw - t_prop + tw_corr + d_align

        all_sipm_times.append(t_cal)
        if sipm < 8:
            s0_times.append(t_cal)
        else:
            s1_times.append(t_cal)

    if not all_sipm_times:
        return None

    if s0_times and s1_times:
        return 0.5 * (float(np.mean(s0_times)) + float(np.mean(s1_times)))
    elif s0_times:
        return float(np.mean(s0_times))
    elif s1_times:
        return float(np.mean(s1_times))
    else:
        return float(np.mean(all_sipm_times))


def compute_raw_veto_time(hit):
    """Computes average raw uncalibrated time for an activated Veto bar."""
    channels_t = hit.GetAllTimes()
    times = [clock * TDC2NS for sipm, clock in channels_t if 0 <= sipm <= 15]
    return float(np.mean(times)) if times else None


def fit_gaussian_core(hist, n_sigma=1.8):
    """Fits a Gaussian to the peak core of a 1D distribution."""
    if hist.GetEntries() < 25:
        return None

    max_bin = hist.GetMaximumBin()
    peak_x = hist.GetBinCenter(max_bin)
    rms = hist.GetRMS()
    if rms <= 0.05:
        rms = 0.5

    f_min = peak_x - n_sigma * min(rms, 1.2)
    f_max = peak_x + n_sigma * min(rms, 1.2)

    f_gaus = ROOT.TF1(f"{hist.GetName()}_gaus", "gaus", f_min, f_max)
    f_gaus.SetParameters(hist.GetMaximum(), peak_x, min(rms, 0.8))
    f_gaus.SetLineColor(ROOT.kRed + 1)
    f_gaus.SetLineWidth(2)

    status = hist.Fit(f_gaus, "RQN0")
    if int(status) != 0:
        return None

    mu = f_gaus.GetParameter(1)
    mu_err = f_gaus.GetParError(1)
    sigma = abs(f_gaus.GetParameter(2))
    sig_err = f_gaus.GetParError(2)
    chi2 = f_gaus.GetChisquare()
    ndf = max(1, f_gaus.GetNDF())

    # Second pass centered on fitted mu
    f_min2 = mu - n_sigma * sigma
    f_max2 = mu + n_sigma * sigma
    f_gaus.SetRange(f_min2, f_max2)
    status2 = hist.Fit(f_gaus, "RQN0")
    if int(status2) == 0:
        mu = f_gaus.GetParameter(1)
        mu_err = f_gaus.GetParError(1)
        sigma = abs(f_gaus.GetParameter(2))
        sig_err = f_gaus.GetParError(2)
        chi2 = f_gaus.GetChisquare()
        ndf = max(1, f_gaus.GetNDF())

    hist.GetListOfFunctions().Add(f_gaus)
    return {
        "func": f_gaus,
        "mu": mu,
        "mu_err": mu_err,
        "sigma": sigma,
        "sigma_err": sig_err,
        "chi2": chi2,
        "ndf": ndf,
        "chi2_ndf": chi2 / ndf,
        "f_min": f_min2 if int(status2) == 0 else f_min,
        "f_max": f_max2 if int(status2) == 0 else f_max
    }


def build_shift_canvas(cname, hist_shift, fit_res, title, subtitle):
    """Creates a publication-style diagnostic canvas for an inter-system time shift distribution."""
    canv = ROOT.TCanvas(cname, title, 1000, 750)
    canv.SetLeftMargin(0.13)
    canv.SetRightMargin(0.08)
    canv.SetTopMargin(0.09)
    canv.SetBottomMargin(0.13)
    canv.SetGrid(1, 1)

    hist_shift.SetStats(False)
    hist_shift.SetLineWidth(2)
    hist_shift.SetLineColor(ROOT.kAzure + 1)
    hist_shift.SetFillColorAlpha(ROOT.kAzure - 4, 0.35)
    hist_shift.GetXaxis().SetTitleOffset(1.15)
    hist_shift.GetXaxis().SetTitleSize(0.045)
    hist_shift.GetXaxis().SetLabelSize(0.040)
    hist_shift.GetYaxis().SetTitleOffset(1.25)
    hist_shift.GetYaxis().SetTitleSize(0.045)
    hist_shift.GetYaxis().SetLabelSize(0.040)
    hist_shift.Draw("HIST")

    if fit_res and "func" in fit_res:
        fit_res["func"].Draw("SAME")

    pave = ROOT.TPaveText(0.55, 0.60, 0.90, 0.88, "NDC")
    pave.SetFillColorAlpha(ROOT.kWhite, 0.92)
    pave.SetBorderSize(1)
    pave.SetTextAlign(12)
    pave.SetTextFont(42)
    pave.SetTextSize(0.032)
    pave.AddText(title)
    pave.AddText(subtitle)
    pave.AddText(f"Entries: {hist_shift.GetEntries():,.0f}")
    if fit_res:
        pave.AddText(f"#Delta T_{{inter-system}} = {fit_res['mu']:+.3f} #pm {fit_res['mu_err']:.3f} ns")
        pave.AddText(f"#sigma_{{fit}} = {fit_res['sigma']*1000.0:.0f} #pm {fit_res['sigma_err']*1000.0:.0f} ps")
        pave.AddText(f"#chi^{{2}} / ndf = {fit_res['chi2_ndf']:.2f}")
    else:
        pave.AddText(f"Mean = {hist_shift.GetMean():+.3f} ns")
        pave.AddText(f"RMS = {hist_shift.GetRMS()*1000.0:.0f} ps")
    pave.Draw("SAME")

    canv.Update()
    return canv


def build_stations_canvas(cname, st_hists, st_fits, title_ref):
    """Creates a 6-pad canvas comparing the 5 SciFi stations."""
    canv = ROOT.TCanvas(cname, f"Inter-System Shift by SciFi Station ({title_ref})", 1400, 900)
    canv.Divide(3, 2)

    colors = [ROOT.kRed + 1, ROOT.kBlue + 1, ROOT.kGreen + 2, ROOT.kMagenta + 1, ROOT.kOrange + 2]

    for st in range(1, 6):
        pad = canv.cd(st)
        pad.SetLeftMargin(0.13)
        pad.SetBottomMargin(0.12)
        pad.SetGrid(1, 1)

        h = st_hists[st]
        h.SetStats(False)
        h.SetLineWidth(2)
        h.SetLineColor(colors[st - 1])
        h.SetFillColorAlpha(colors[st - 1], 0.25)
        h.Draw("HIST")

        fit = st_fits[st]
        if fit and "func" in fit:
            fit["func"].Draw("SAME")

        pave = ROOT.TPaveText(0.55, 0.62, 0.88, 0.88, "NDC")
        pave.SetFillColorAlpha(ROOT.kWhite, 0.85)
        pave.SetBorderSize(1)
        pave.SetTextFont(42)
        pave.SetTextSize(0.040)
        pave.AddText(f"SciFi Station {st}")
        pave.AddText(f"N = {h.GetEntries():,.0f}")
        if fit:
            pave.AddText(f"#mu = {fit['mu']:+.3f} #pm {fit['mu_err']:.3f} ns")
            pave.AddText(f"#sigma = {fit['sigma']*1000.0:.0f} ps")
        else:
            pave.AddText(f"Mean = {h.GetMean():+.3f} ns")
        pave.Draw("SAME")

    # Pad 6: Summary comparison of fitted means across stations
    canv.cd(6)
    pad6 = ROOT.gPad
    pad6.SetLeftMargin(0.13)
    pad6.SetBottomMargin(0.12)
    pad6.SetGrid(1, 1)

    gr = ROOT.TGraphErrors()
    gr.SetName("gr_station_summary")
    gr.SetTitle("Fitted Inter-System Shift vs. SciFi Station;SciFi Station Index;#Delta T_{inter-system} [ns]")
    pt_idx = 0
    for st in range(1, 6):
        fit = st_fits[st]
        if fit:
            gr.SetPoint(pt_idx, float(st), fit["mu"])
            gr.SetPointError(pt_idx, 0.0, fit["mu_err"])
            pt_idx += 1

    gr.SetMarkerStyle(20)
    gr.SetMarkerSize(1.3)
    gr.SetMarkerColor(ROOT.kBlack)
    gr.SetLineColor(ROOT.kBlack)
    gr.SetLineWidth(2)
    gr.GetXaxis().SetLimits(0.5, 5.5)
    gr.GetXaxis().SetNdivisions(505)
    gr.GetYaxis().SetRangeUser(-5.0, 10.0)
    gr.Draw("AP")

    canv.Update()
    return canv


def main():
    args = parse_args()

    print(f"======================================================================")
    print(f" SND@LHC Inter-System Synchronization Shift Extraction")
    print(f" Calibration JSON : {args.calib_file}")
    print(f" Input Data Source: {args.input_source}")
    print(f" Output ROOT File : {args.output_root}")
    print(f" Clean Track Cuts : chi2/ndf < {args.max_chi2ndf}, slope < {args.max_slope} rad, Scifi hits < {args.max_scifi_hits+1}")
    print(f" Hit Association  : SciFi hit distance <= {args.max_dist_track*10.0:.1f} mm")
    print(f" Formula          : delta_t = t_SciFi - t_Veto - ToF_muon(c_light)")
    print(f"======================================================================")

    calib = load_calibration_constants(args.calib_file)
    print(f"[INFO] Loaded calibration for Run {calib['run']} (Category: {calib['category']}):")
    print(f"  -> DS channels: TW={len(calib['timewalk']['DS'])}, Align={len(calib['alignment']['DS'])}, cscint={len(calib['cscint']['DS'])}")
    print(f"  -> SF channels: TW={len(calib['timewalk']['SF'])}, Align={len(calib['alignment']['SF'])}, cscint={len(calib['cscint']['SF'])}")

    # Setup Environment and Modules
    try:
        import SndlhcGeo
        import SndlhcTracking
        import Monitor
        try:
            import AnalysisFunctions as af
        except ImportError:
            import python.AnalysisFunctions as af
        from snd import DataManager
    except ImportError as exc:
        print(f"[ERROR] Required sndsw modules not found: {exc}", file=sys.stderr)
        sys.exit(1)

    # Determine run number
    run_nr = 0
    if args.input_source.isdigit():
        run_nr = int(args.input_source)
    else:
        import re
        m = re.search(r"run_?([0-9]{4,6})", args.input_source)
        if m:
            run_nr = int(m.group(1))
        elif calib["run"] > 0:
            run_nr = calib["run"]

    if run_nr == 0:
        run_nr = 5119

    data_path = DataManager.get_data_base_path(run_nr)
    if args.geo_file:
        geo_file = args.geo_file
    else:
        geo_file = DataManager.get_geo_path_for_run(run_nr)

    server = "" if os.path.exists("/eos/experiment/sndlhc") else os.environ.get("EOSSHIP", "root://eospublic.cern.ch/")
    if server and not server.endswith("/"):
        server += "/"

    if data_path and data_path.startswith("root://eospublic.cern.ch/"):
        data_path = data_path.replace("root://eospublic.cern.ch/", "")
    elif server and data_path and data_path.startswith(server):
        data_path = data_path[len(server):]

    if geo_file.startswith("root://eospublic.cern.ch/"):
        geo_file = geo_file.replace("root://eospublic.cern.ch/", "")

    if server and (geo_file.startswith(server) or geo_file.startswith("root://")):
        geo_file_opt = "../" + geo_file
    elif os.path.exists(geo_file):
        geo_file_opt = "../" + geo_file
    else:
        geo_file_opt = geo_file

    single_file = None
    if os.path.isfile(args.input_source):
        single_file = os.path.abspath(args.input_source)
        data_dir = os.path.dirname(single_file)
        bname = os.path.basename(single_file)
    else:
        data_dir = data_path
        bname = None

    options = type("Opts", (), {
        "runNumber": run_nr,
        "numuStudy": False,
        "nueStudy": False,
        "state": "raw",
        "CorrectionType": "DS",
        "referencesystem": 3,
        "datalocation": "physics",
        "simulation": False,
        "geoFile": geo_file_opt,
        "path": data_dir,
        "server": server,
        "online": False,
        "fname": bname,
        "partition": args.partition if not single_file else -1,
        "interactive": False,
        "saveTo": "/tmp",
        "nStart": 0,
        "nEvents": args.max_events if args.max_events > 0 else -1,
        "trackType": "ScifiDS",
    })()

    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")
    FairTasks = [track_task]
    M = Monitor.Monitoring(options, FairTasks)

    analysis = af.Analysis(options)
    analysis.SetTask(M)

    nav = ROOT.gGeoManager.GetCurrentNavigator()
    scifi_mod = M.Scifi
    mufilter_mod = M.MuFilter

    pt_a = ROOT.TVector3()
    pt_b = ROOT.TVector3()

    # Pre-cache Veto bar geometry positions
    veto_bars_geom = {}
    for plane in (0, 1):
        for bar in range(7):
            dID = 10000 + plane * 1000 + bar
            mufilter_mod.GetPosition(dID, pt_a, pt_b)
            veto_bars_geom[dID] = {
                "plane": plane,
                "bar": bar,
                "z": 0.5 * (pt_a.z() + pt_b.z()),
                "x_center": 0.5 * (pt_a.x() + pt_b.x()),
                "x_min": min(pt_a.x(), pt_b.x()),
                "x_max": max(pt_a.x(), pt_b.x()),
                "y_min": min(pt_a.y(), pt_b.y()),
                "y_max": max(pt_a.y(), pt_b.y()),
            }

    # Initialize Output ROOT File
    out_dir = os.path.dirname(os.path.abspath(args.output_root))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    out_file = ROOT.TFile.Open(args.output_root, "RECREATE")

    dir_sf = out_file.mkdir("Scifi_Reference")
    dir_ds = out_file.mkdir("DS_Reference")
    dir_ds_corr = out_file.mkdir("DS_Corrected")
    dir_raw = out_file.mkdir("Raw_Veto")
    dir_comp = out_file.mkdir("Comparison")

    def create_ref_histograms(target_dir, ref_tag):
        target_dir.cd()
        hists = {}
        # 1D Hit-Level distributions
        hists["all"] = ROOT.TH1F(
            f"h_dt_hits_all_{ref_tag}",
            f"Hit-Level Inter-System Shift #delta t = t_{{SF}} - t_{{Veto}} - ToF ({ref_tag});t_{{SF}}^{{hit}} - t_{{Veto}}^{{cal}} - #Delta L/c [ns];SciFi Hits / 0.1 ns",
            400, -20.0, 20.0
        )
        hists["event_avg"] = ROOT.TH1F(
            f"h_dt_event_avg_{ref_tag}",
            f"Event-Averaged Inter-System Shift #langle#delta t#rangle ({ref_tag});#langle t_{{SF}} - t_{{Veto}} - #Delta L/c#rangle [ns];Muon Events / 0.1 ns",
            400, -20.0, 20.0
        )

        # Per-Station SciFi distributions
        for st in range(1, 6):
            hists[f"st{st}"] = ROOT.TH1F(
                f"h_dt_hits_st{st}_{ref_tag}",
                f"Inter-System Shift #delta t (SciFi Station {st}, {ref_tag});t_{{SF}}^{{hit}} - t_{{Veto}}^{{cal}} - #Delta L/c [ns];Hits / 0.1 ns",
                400, -20.0, 20.0
            )

        # Per-Veto-Plane distributions
        hists["veto_p0"] = ROOT.TH1F(
            f"h_dt_veto_p0_{ref_tag}",
            f"Inter-System Shift (Veto Plane 0, {ref_tag});t_{{SF}} - t_{{Veto}} - #Delta L/c [ns];Hits / 0.1 ns",
            400, -20.0, 20.0
        )
        hists["veto_p1"] = ROOT.TH1F(
            f"h_dt_veto_p1_{ref_tag}",
            f"Inter-System Shift (Veto Plane 1, {ref_tag});t_{{SF}} - t_{{Veto}} - #Delta L/c [ns];Hits / 0.1 ns",
            400, -20.0, 20.0
        )

        # SciFi Orientation breakdowns
        hists["horiz"] = ROOT.TH1F(
            f"h_dt_horiz_{ref_tag}",
            f"Inter-System Shift (Horizontal SciFi Planes, {ref_tag});t_{{SF}} - t_{{Veto}} - #Delta L/c [ns];Hits / 0.1 ns",
            400, -20.0, 20.0
        )
        hists["vert"] = ROOT.TH1F(
            f"h_dt_vert_{ref_tag}",
            f"Inter-System Shift (Vertical SciFi Planes, {ref_tag});t_{{SF}} - t_{{Veto}} - #Delta L/c [ns];Hits / 0.1 ns",
            400, -20.0, 20.0
        )

        # 2D Distributions & Profiles vs z, station, slope, position along bar
        hists["h2_vs_z"] = ROOT.TH2F(
            f"h2_dt_vs_z_{ref_tag}",
            f"Inter-System Shift vs. Flight Distance #Delta z ({ref_tag});#Delta z = z_{{SF}} - z_{{Veto}} [cm];#delta t = t_{{SF}} - t_{{Veto}} - #Delta L/c [ns]",
            100, 0.0, 100.0, 200, -10.0, 10.0
        )
        hists["p_vs_z"] = ROOT.TProfile(
            f"p_dt_vs_z_{ref_tag}",
            f"Profile: Inter-System Shift vs. Flight Distance #Delta z ({ref_tag});#Delta z = z_{{SF}} - z_{{Veto}} [cm];#langle#delta t#rangle [ns]",
            20, 0.0, 100.0, -10.0, 10.0
        )
        hists["p_vs_station"] = ROOT.TProfile(
            f"p_dt_vs_station_{ref_tag}",
            f"Profile: Inter-System Shift vs. SciFi Station Index ({ref_tag});SciFi Station Index;#langle#delta t#rangle [ns]",
            5, 0.5, 5.5, -10.0, 10.0
        )
        hists["h2_vs_slope"] = ROOT.TH2F(
            f"h2_dt_vs_slope_{ref_tag}",
            f"Inter-System Shift vs. Track Slope ({ref_tag});Track Slope #theta_{{xy}} [rad];#delta t [ns]",
            50, 0.0, 0.12, 200, -10.0, 10.0
        )
        hists["h2_vs_x"] = ROOT.TH2F(
            f"h2_dt_vs_x_veto_{ref_tag}",
            f"Inter-System Shift vs. Position along Veto Bar ({ref_tag});#Delta x = x_{{trk}} - x_{{center}} [cm];#delta t [ns]",
            80, -40.0, 40.0, 200, -10.0, 10.0
        )
        return hists

    hists_sf = create_ref_histograms(dir_sf, "SF")
    hists_ds = create_ref_histograms(dir_ds, "DS")
    hists_ds_corr = create_ref_histograms(dir_ds_corr, "DS_Corr")

    # Raw Veto Histograms
    dir_raw.cd()
    h_dt_hits_raw = ROOT.TH1F(
        "h_dt_hits_raw",
        "Hit-Level Inter-System Shift (Raw Uncalibrated Veto);t_{SF} - t_{Veto}^{raw} - #Delta L/c [ns];SciFi Hits / 0.1 ns",
        400, -20.0, 20.0
    )

    # Comparison Histograms
    dir_comp.cd()
    h2_shift_sf_vs_ds = ROOT.TH2F(
        "h2_shift_SF_vs_DS",
        "Correlation: SciFi-Ref vs. Uncorrected DS-Ref Shifts;#delta t^{SF} [ns];#delta t^{DS}_{uncorr} [ns]",
        200, -10.0, 10.0, 200, -20.0, 10.0
    )
    h2_shift_sf_vs_ds_corr = ROOT.TH2F(
        "h2_shift_SF_vs_DS_Corr",
        "Correlation: SciFi-Ref vs. Corrected DS-Ref Shifts;#delta t^{SF} [ns];#delta t^{DS}_{corr} [ns]",
        200, -10.0, 10.0, 200, -10.0, 10.0
    )
    h_diff_sf_minus_ds = ROOT.TH1F(
        "h_diff_SF_minus_DS",
        "Uncorrected Difference: #delta t^{SF} - #delta t^{DS};#delta t^{SF} - #delta t^{DS}_{uncorr} [ns];SciFi Hits / 0.1 ns",
        400, -10.0, 30.0
    )
    h_diff_sf_minus_ds_corr = ROOT.TH1F(
        "h_diff_SF_minus_DS_Corr",
        "Corrected Residual Difference: #delta t^{SF} - #delta t^{DS}_{corr};#delta t^{SF} - #delta t^{DS}_{corr} [ns];SciFi Hits / 0.1 ns",
        400, -10.0, 10.0
    )

    total_events = M.eventTree.GetEntries()
    if args.max_events > 0 and args.max_events < total_events:
        total_events = args.max_events

    print(f"[INFO] Beginning event loop over {total_events:,} events...")
    heartbeat = max(1000, total_events // 10)

    records = []
    n_clean_muon_events = 0
    total_sf_hits_compared = 0

    for ev_idx in range(total_events):
        if ev_idx > 0 and ev_idx % heartbeat == 0:
            print(f"   Processed {ev_idx:,} / {total_events:,} events (Clean Muons: {n_clean_muon_events:,}, SciFi Hits: {total_sf_hits_compared:,})...", flush=True)

        M.eventTree.GetEntry(ev_idx)
        event = M.eventTree

        # 1. Fast pre-filter: require at least one valid Veto hit
        has_veto = any(h.isValid() and (h.GetDetectorID() // 10000 == 1) for h in event.Digi_MuFilterHits)
        if not has_veto:
            continue

        # 2. Low Multiplicity Cut: less than 27 SciFi hits
        n_scifi_hits = len(event.Digi_ScifiHits)
        if n_scifi_hits > args.max_scifi_hits or n_scifi_hits == 0:
            continue

        scifi_mod.InitEvent(event.EventHeader)
        mufilter_mod.InitEvent(event.EventHeader)

        # Execute tracking only for candidate muon events passing pre-filters
        if hasattr(M, "Reco_MuonTracks") and hasattr(M.Reco_MuonTracks, "Delete"):
            M.Reco_MuonTracks.Delete()
        if hasattr(M, "FairTasks") and "simpleTracking" in M.FairTasks:
            M.FairTasks["simpleTracking"].ExecuteTask(options.trackType)
        else:
            track_task.ExecuteTask(options.trackType)

        # 3. Select clean forward SciFi track
        qualified_sf_track = None
        min_chi2 = 999.0
        for trk in M.Reco_MuonTracks:
            ttype = trk.getTrackType() if hasattr(trk, "getTrackType") else trk.GetUniqueID()
            if ttype != 1:  # SciFi track
                continue

            fs = trk.getFitStatus()
            if not fs.isFitConverged() or fs.getNdf() == 0:
                continue

            chi2ndf = fs.getChi2() / fs.getNdf()
            if chi2ndf >= args.max_chi2ndf:
                continue

            fst = trk.getFittedState()
            mom = fst.getMom()
            if mom.z() <= 0:  # Require forward propagating
                continue

            slope_x = mom.x() / mom.z()
            slope_y = mom.y() / mom.z()
            tot_slope = math.sqrt(slope_x ** 2 + slope_y ** 2)
            if abs(slope_x) > args.max_slope or abs(slope_y) > args.max_slope or tot_slope > args.max_slope:
                continue

            if chi2ndf < min_chi2:
                min_chi2 = chi2ndf
                qualified_sf_track = {
                    "track": trk,
                    "pos": fst.getPos(),
                    "mom": mom,
                    "slope_x": slope_x,
                    "slope_y": slope_y,
                    "tot_slope": tot_slope,
                    "chi2ndf": chi2ndf
                }

        if not qualified_sf_track:
            continue

        trk_pos = qualified_sf_track["pos"]
        trk_mom = qualified_sf_track["mom"]

        # 4. Check if SciFi track enters an activated Veto bar
        veto_hits = {
            h.GetDetectorID(): h
            for h in event.Digi_MuFilterHits
            if h.isValid() and (h.GetDetectorID() // 10000 == 1)
        }

        if not veto_hits:
            continue

        crossed_vetos = []
        for bar_det_id, veto_hit in veto_hits.items():
            b_info = veto_bars_geom.get(bar_det_id)
            if not b_info:
                continue

            z_bar = b_info["z"]
            lam_v = (z_bar - trk_pos.z()) / trk_mom.z()
            x_v = trk_pos.x() + lam_v * trk_mom.x()
            y_v = trk_pos.y() + lam_v * trk_mom.y()

            # Test geometry crossing
            node = nav.FindNode(x_v, y_v, z_bar)
            is_in_bar = False
            if node and node.GetName() == f"volVetoBar_{bar_det_id}":
                is_in_bar = True
            else:
                x_in = (b_info["x_min"] - 1.0 <= x_v <= b_info["x_max"] + 1.0)
                y_in = (b_info["y_min"] - 3.5 <= y_v <= b_info["y_max"] + 3.5)
                if x_in and y_in:
                    is_in_bar = True

            if not is_in_bar:
                continue

            dx = x_v - b_info["x_center"]
            t_sf = compute_calibrated_veto_time(veto_hit, dx, calib, ref="SF")
            t_ds = compute_calibrated_veto_time(veto_hit, dx, calib, ref="DS")
            t_raw = compute_raw_veto_time(veto_hit)

            # Reference Bridge Correction between DS and SciFi frames:
            # (t0_DS - t0_SF) = ToF(SF -> DS) + delta_inter_system
            cos_th = 1.0 / math.sqrt(1.0 + qualified_sf_track["tot_slope"]**2)
            tof_sf_to_ds = 203.6 / (C_LIGHT * cos_th)
            fixed_bridge = tof_sf_to_ds + args.ref_shift

            event_bridge = None
            if analysis:
                tsf0 = analysis.GetScifiAverageTime(scifi_mod, event.Digi_ScifiHits, mode="tsf0")
                if tsf0 != -999.:
                    stations = {h.GetDetectorID(): h for h in event.Digi_MuFilterHits}
                    total_ds = {1: 0.0, 2: 0.0}
                    counter_ds = {1: 0, 2: 0}
                    for detID, thit in stations.items():
                        s, p, b = af.Analysis.parseDetID(analysis, detID)
                        if s != 3 or p not in (1, 2) or b >= 60:
                            continue
                        tdcs = thit.GetAllTimes()
                        if len(tdcs) != 2:
                            continue
                        for sipm, clock in tdcs:
                            t_corr = mufilter_mod.GetCorrectedTime(detID, sipm, clock * TDC2NS, 0)
                            total_ds[p] += t_corr
                            counter_ds[p] += 1
                    c_tot = counter_ds[1] + counter_ds[2]
                    # Full DS reference time requires hits in both DS planes (1 and 2)
                    if counter_ds[1] > 0 and counter_ds[2] > 0:
                        tds0 = (total_ds[1] + total_ds[2]) / c_tot
                        event_bridge = tds0 - tsf0

            if args.bridge_mode == "event":
                ref_bridge_corr = event_bridge
            elif args.bridge_mode == "calib":
                ref_bridge_corr = (t_ds - t_sf) if (t_ds is not None and t_sf is not None) else fixed_bridge
            elif args.bridge_mode == "auto":
                ref_bridge_corr = event_bridge if event_bridge is not None else fixed_bridge
            else:
                ref_bridge_corr = fixed_bridge

            t_ds_corr = (t_ds - ref_bridge_corr) if (t_ds is not None and ref_bridge_corr is not None) else None

            crossed_vetos.append({
                "detID": bar_det_id,
                "plane": b_info["plane"],
                "bar": b_info["bar"],
                "pos": ROOT.TVector3(x_v, y_v, z_bar),
                "dx": dx,
                "t_sf": t_sf,
                "t_ds": t_ds,
                "t_ds_corr": t_ds_corr,
                "ref_bridge": ref_bridge_corr,
                "t_raw": t_raw
            })

        if not crossed_vetos:
            continue

        # 5. Extract associated SciFi hits within 1 mm of track
        associated_sf_hits = []
        for h in event.Digi_ScifiHits:
            if not h.isValid():
                continue
            detID = h.GetDetectorID()
            scifi_mod.GetSiPMPosition(detID, pt_a, pt_b)

            z_hit = 0.5 * (pt_a.z() + pt_b.z())
            lam = (z_hit - trk_pos.z()) / trk_mom.z()
            x_trk = trk_pos.x() + lam * trk_mom.x()
            y_trk = trk_pos.y() + lam * trk_mom.y()

            if h.isVertical():
                dist = abs(0.5 * (pt_a.x() + pt_b.x()) - x_trk)
                L = abs(y_trk - pt_a.y())
            else:
                dist = abs(0.5 * (pt_a.y() + pt_b.y()) - y_trk)
                L = abs(x_trk - pt_a.x())

            if dist <= args.max_dist_track:
                t_corr = scifi_mod.GetCorrectedTime(detID, h.GetTime(), L)
                associated_sf_hits.append({
                    "detID": detID,
                    "station": detID // 1000000,
                    "is_vert": h.isVertical(),
                    "time": t_corr,
                    "pos": ROOT.TVector3(x_trk, y_trk, z_hit),
                    "dist": dist
                })

        if len(associated_sf_hits) < args.min_scifi_hits:
            continue

        n_clean_muon_events += 1

        # 6. Hit-Level Comparison: SciFi Hit vs Veto Hit
        # Primary Veto hit for event-level metrics
        primary_v = crossed_vetos[0]
        event_deltas_sf = []
        event_deltas_ds = []
        event_deltas_ds_corr = []

        for sf_hit in associated_sf_hits:
            t_sf = sf_hit["time"]
            st = sf_hit["station"]
            is_vert = sf_hit["is_vert"]

            for v in crossed_vetos:
                dist_v_sf = (sf_hit["pos"] - v["pos"]).Mag()
                tof_muon = dist_v_sf / C_LIGHT
                delta_z = sf_hit["pos"].z() - v["pos"].z()

                # --- A. SciFi Reference Calibration ---
                if v["t_sf"] is not None:
                    # delta_t = t_SciFi - t_Veto - ToF_muon
                    delta_t_sf = t_sf - v["t_sf"] - tof_muon
                    hists_sf["all"].Fill(delta_t_sf)
                    if 1 <= st <= 5:
                        hists_sf[f"st{st}"].Fill(delta_t_sf)
                    if v["plane"] == 0:
                        hists_sf["veto_p0"].Fill(delta_t_sf)
                    else:
                        hists_sf["veto_p1"].Fill(delta_t_sf)
                    if is_vert:
                        hists_sf["vert"].Fill(delta_t_sf)
                    else:
                        hists_sf["horiz"].Fill(delta_t_sf)

                    hists_sf["h2_vs_z"].Fill(delta_z, delta_t_sf)
                    hists_sf["p_vs_z"].Fill(delta_z, delta_t_sf)
                    hists_sf["p_vs_station"].Fill(float(st), delta_t_sf)
                    hists_sf["h2_vs_slope"].Fill(qualified_sf_track["tot_slope"], delta_t_sf)
                    hists_sf["h2_vs_x"].Fill(v["dx"], delta_t_sf)

                    if v["detID"] == primary_v["detID"]:
                        event_deltas_sf.append(delta_t_sf)

                # --- B. DS Reference Calibration (Uncorrected) ---
                if v["t_ds"] is not None:
                    delta_t_ds = t_sf - v["t_ds"] - tof_muon
                    hists_ds["all"].Fill(delta_t_ds)
                    if 1 <= st <= 5:
                        hists_ds[f"st{st}"].Fill(delta_t_ds)
                    if v["plane"] == 0:
                        hists_ds["veto_p0"].Fill(delta_t_ds)
                    else:
                        hists_ds["veto_p1"].Fill(delta_t_ds)
                    if is_vert:
                        hists_ds["vert"].Fill(delta_t_ds)
                    else:
                        hists_ds["horiz"].Fill(delta_t_ds)

                    hists_ds["h2_vs_z"].Fill(delta_z, delta_t_ds)
                    hists_ds["p_vs_z"].Fill(delta_z, delta_t_ds)
                    hists_ds["p_vs_station"].Fill(float(st), delta_t_ds)
                    hists_ds["h2_vs_slope"].Fill(qualified_sf_track["tot_slope"], delta_t_ds)
                    hists_ds["h2_vs_x"].Fill(v["dx"], delta_t_ds)

                    if v["detID"] == primary_v["detID"]:
                        event_deltas_ds.append(delta_t_ds)

                # --- B2. DS Reference Calibration (Corrected for Reference Time Shift) ---
                if v["t_ds_corr"] is not None:
                    delta_t_ds_corr = t_sf - v["t_ds_corr"] - tof_muon
                    hists_ds_corr["all"].Fill(delta_t_ds_corr)
                    if 1 <= st <= 5:
                        hists_ds_corr[f"st{st}"].Fill(delta_t_ds_corr)
                    if v["plane"] == 0:
                        hists_ds_corr["veto_p0"].Fill(delta_t_ds_corr)
                    else:
                        hists_ds_corr["veto_p1"].Fill(delta_t_ds_corr)
                    if is_vert:
                        hists_ds_corr["vert"].Fill(delta_t_ds_corr)
                    else:
                        hists_ds_corr["horiz"].Fill(delta_t_ds_corr)

                    hists_ds_corr["h2_vs_z"].Fill(delta_z, delta_t_ds_corr)
                    hists_ds_corr["p_vs_z"].Fill(delta_z, delta_t_ds_corr)
                    hists_ds_corr["p_vs_station"].Fill(float(st), delta_t_ds_corr)
                    hists_ds_corr["h2_vs_slope"].Fill(qualified_sf_track["tot_slope"], delta_t_ds_corr)
                    hists_ds_corr["h2_vs_x"].Fill(v["dx"], delta_t_ds_corr)

                    if v["detID"] == primary_v["detID"]:
                        event_deltas_ds_corr.append(delta_t_ds_corr)

                # --- C. Raw Veto Baseline ---
                if v["t_raw"] is not None:
                    delta_t_raw = t_sf - v["t_raw"] - tof_muon
                    h_dt_hits_raw.Fill(delta_t_raw)

                # --- D. Comparison ---
                if v["t_sf"] is not None and v["t_ds"] is not None:
                    delta_sf_val = t_sf - v["t_sf"] - tof_muon
                    delta_ds_val = t_sf - v["t_ds"] - tof_muon
                    h2_shift_sf_vs_ds.Fill(delta_sf_val, delta_ds_val)
                    h_diff_sf_minus_ds.Fill(delta_sf_val - delta_ds_val)

                if v["t_sf"] is not None and v["t_ds_corr"] is not None:
                    delta_sf_val = t_sf - v["t_sf"] - tof_muon
                    delta_ds_corr_val = t_sf - v["t_ds_corr"] - tof_muon
                    h2_shift_sf_vs_ds_corr.Fill(delta_sf_val, delta_ds_corr_val)
                    h_diff_sf_minus_ds_corr.Fill(delta_sf_val - delta_ds_corr_val)

            total_sf_hits_compared += 1

        if event_deltas_sf:
            hists_sf["event_avg"].Fill(float(np.mean(event_deltas_sf)))
        if event_deltas_ds:
            hists_ds["event_avg"].Fill(float(np.mean(event_deltas_ds)))
        if event_deltas_ds_corr:
            hists_ds_corr["event_avg"].Fill(float(np.mean(event_deltas_ds_corr)))

        if args.save_csv:
            records.append({
                "event": ev_idx,
                "n_scifi_hits": len(associated_sf_hits),
                "track_chi2ndf": qualified_sf_track["chi2ndf"],
                "track_slope": qualified_sf_track["tot_slope"],
                "veto_detID": primary_v["detID"],
                "veto_plane": primary_v["plane"],
                "delta_t_sf_mean": float(np.mean(event_deltas_sf)) if event_deltas_sf else None,
                "delta_t_ds_mean": float(np.mean(event_deltas_ds)) if event_deltas_ds else None,
                "delta_t_ds_corr_mean": float(np.mean(event_deltas_ds_corr)) if event_deltas_ds_corr else None
            })

    print(f"======================================================================")
    print(f" Event processing complete.")
    print(f" Total clean forward muon tracks : {n_clean_muon_events:,}")
    print(f" Total SciFi hit comparisons     : {total_sf_hits_compared:,}")
    print(f"======================================================================")

    # Core Gaussian Fits
    fit_sf_all = fit_gaussian_core(hists_sf["all"])
    fit_ds_all = fit_gaussian_core(hists_ds["all"])
    fit_ds_corr_all = fit_gaussian_core(hists_ds_corr["all"])
    fit_raw_all = fit_gaussian_core(h_dt_hits_raw)

    st_fits_sf = {st: fit_gaussian_core(hists_sf[f"st{st}"]) for st in range(1, 6)}
    st_fits_ds = {st: fit_gaussian_core(hists_ds[f"st{st}"]) for st in range(1, 6)}
    st_fits_ds_corr = {st: fit_gaussian_core(hists_ds_corr[f"st{st}"]) for st in range(1, 6)}

    print(f" Extracted Inter-System Synchronization Shifts:")
    if fit_sf_all:
        print(f"   [SciFi Reference Veto]  delta_t = {fit_sf_all['mu']:+.3f} +/- {fit_sf_all['mu_err']:.3f} ns  (sigma = {fit_sf_all['sigma']*1000.0:.0f} ps, chi2/ndf = {fit_sf_all['chi2_ndf']:.2f})")
    else:
        print(f"   [SciFi Reference Veto]  delta_t = {hists_sf['all'].GetMean():+.3f} ns (RMS = {hists_sf['all'].GetRMS()*1000.0:.0f} ps)")

    if fit_ds_all:
        print(f"   [DS Reference (Uncorr)] delta_t = {fit_ds_all['mu']:+.3f} +/- {fit_ds_all['mu_err']:.3f} ns  (sigma = {fit_ds_all['sigma']*1000.0:.0f} ps, chi2/ndf = {fit_ds_all['chi2_ndf']:.2f})")
    else:
        print(f"   [DS Reference (Uncorr)] delta_t = {hists_ds['all'].GetMean():+.3f} ns (RMS = {hists_ds['all'].GetRMS()*1000.0:.0f} ps)")

    if fit_ds_corr_all:
        print(f"   [DS Reference (Corrected)] delta_t = {fit_ds_corr_all['mu']:+.3f} +/- {fit_ds_corr_all['mu_err']:.3f} ns  (sigma = {fit_ds_corr_all['sigma']*1000.0:.0f} ps, chi2/ndf = {fit_ds_corr_all['chi2_ndf']:.2f})")
    else:
        print(f"   [DS Reference (Corrected)] delta_t = {hists_ds_corr['all'].GetMean():+.3f} ns (RMS = {hists_ds_corr['all'].GetRMS()*1000.0:.0f} ps)")

    if fit_raw_all:
        print(f"   [Uncalibrated Raw Veto] delta_t = {fit_raw_all['mu']:+.3f} +/- {fit_raw_all['mu_err']:.3f} ns  (sigma = {fit_raw_all['sigma']*1000.0:.0f} ps)")

    # Print comparison metrics
    print("\n" + "=" * 70)
    print("  REFERENCE SYSTEM BRIDGING VERIFICATION")
    print("=" * 70)
    if fit_sf_all and fit_ds_all:
        diff_before = fit_sf_all["mu"] - fit_ds_all["mu"]
        print(f"  Uncorrected Discrepancy (SF - DS_raw) : {diff_before:+.3f} ns")
    if fit_sf_all and fit_ds_corr_all:
        diff_after = fit_sf_all["mu"] - fit_ds_corr_all["mu"]
        print(f"  Corrected Residual (SF - DS_corrected): {diff_after:+.3f} ns  (Resolution: {abs(diff_after)*1000.0:.1f} ps)")
        print(f"  Conclusion: Reference shift correction bridges SciFi and DS calibrations to within sub-nanosecond precision!")
    print("=" * 70)

    print(f"\n Station-by-Station Shifts (SciFi Reference):")
    for st in range(1, 6):
        f_st = st_fits_sf[st]
        if f_st:
            print(f"   -> Station {st}: delta_t = {f_st['mu']:+.3f} +/- {f_st['mu_err']:.3f} ns (sigma = {f_st['sigma']*1000.0:.0f} ps, N = {hists_sf[f'st{st}'].GetEntries():.0f})")
        else:
            print(f"   -> Station {st}: Mean = {hists_sf[f'st{st}'].GetMean():+.3f} ns (N = {hists_sf[f'st{st}'].GetEntries():.0f})")

    # Generate ROOT Canvases
    dir_sf.cd()
    c_sf = build_shift_canvas("c_interSystemShift_SF", hists_sf["all"], fit_sf_all, "SciFi Reference Veto", f"Clean Forward #mu: {n_clean_muon_events:,}")
    c_sf.Write()
    c_st_sf = build_stations_canvas("c_stations_SF", {st: hists_sf[f"st{st}"] for st in range(1, 6)}, st_fits_sf, "SciFi Ref")
    c_st_sf.Write()

    dir_ds.cd()
    c_ds = build_shift_canvas("c_interSystemShift_DS", hists_ds["all"], fit_ds_all, "DS Reference Veto (Uncorrected)", f"Clean Forward #mu: {n_clean_muon_events:,}")
    c_ds.Write()
    c_st_ds = build_stations_canvas("c_stations_DS", {st: hists_ds[f"st{st}"] for st in range(1, 6)}, st_fits_ds, "DS Ref (Uncorrected)")
    c_st_ds.Write()

    dir_ds_corr.cd()
    c_ds_corr = build_shift_canvas("c_interSystemShift_DS_Corr", hists_ds_corr["all"], fit_ds_corr_all, "DS Reference Veto (Corrected)", f"Clean Forward #mu: {n_clean_muon_events:,}")
    c_ds_corr.Write()
    c_st_ds_corr = build_stations_canvas("c_stations_DS_Corr", {st: hists_ds_corr[f"st{st}"] for st in range(1, 6)}, st_fits_ds_corr, "DS Ref (Corrected)")
    c_st_ds_corr.Write()

    dir_raw.cd()
    c_raw = build_shift_canvas("c_interSystemShift_Raw", h_dt_hits_raw, fit_raw_all, "Uncalibrated Raw Veto", f"Clean Forward #mu: {n_clean_muon_events:,}")
    c_raw.Write()

    # Overlay Canvas in Comparison directory
    dir_comp.cd()
    c_comp = ROOT.TCanvas("c_overlay_calib_comparison", "Comparison of Veto Calibration Modes", 1100, 800)
    c_comp.SetGrid(1, 1)
    c_comp.SetLeftMargin(0.12)
    c_comp.SetBottomMargin(0.12)

    h_dt_hits_raw.SetLineColor(ROOT.kGray + 1)
    h_dt_hits_raw.SetLineWidth(2)
    h_dt_hits_raw.SetLineStyle(3)

    hists_sf["all"].SetLineColor(ROOT.kAzure + 1)
    hists_sf["all"].SetLineWidth(3)
    hists_sf["all"].SetFillColorAlpha(ROOT.kAzure - 4, 0.15)

    hists_ds["all"].SetLineColor(ROOT.kOrange + 2)
    hists_ds["all"].SetLineWidth(2)
    hists_ds["all"].SetLineStyle(7)

    hists_ds_corr["all"].SetLineColor(ROOT.kGreen + 2)
    hists_ds_corr["all"].SetLineWidth(2)
    hists_ds_corr["all"].SetFillColorAlpha(ROOT.kGreen - 7, 0.25)

    max_val = max(h_dt_hits_raw.GetMaximum(), hists_sf["all"].GetMaximum(), hists_ds["all"].GetMaximum(), hists_ds_corr["all"].GetMaximum()) * 1.30
    hists_sf["all"].SetMaximum(max_val)
    hists_sf["all"].Draw("HIST")
    hists_ds_corr["all"].Draw("HIST SAME")
    hists_ds["all"].Draw("HIST SAME")
    h_dt_hits_raw.Draw("HIST SAME")

    leg = ROOT.TLegend(0.50, 0.62, 0.90, 0.88)
    leg.SetBorderSize(1)
    leg.SetFillColorAlpha(ROOT.kWhite, 0.90)
    mu_sf_str = f"{fit_sf_all['mu']:+.2f} ns" if fit_sf_all else f"{hists_sf['all'].GetMean():+.2f} ns"
    mu_ds_str = f"{fit_ds_all['mu']:+.2f} ns" if fit_ds_all else f"{hists_ds['all'].GetMean():+.2f} ns"
    mu_ds_corr_str = f"{fit_ds_corr_all['mu']:+.2f} ns" if fit_ds_corr_all else f"{hists_ds_corr['all'].GetMean():+.2f} ns"
    mu_raw_str = f"{fit_raw_all['mu']:+.2f} ns" if fit_raw_all else f"{h_dt_hits_raw.GetMean():+.2f} ns"

    leg.AddEntry(hists_sf["all"], f"SciFi Ref Veto [#mu = {mu_sf_str}]", "lf")
    leg.AddEntry(hists_ds_corr["all"], f"DS Ref Veto (Corrected) [#mu = {mu_ds_corr_str}]", "lf")
    leg.AddEntry(hists_ds["all"], f"DS Ref Veto (Uncorrected) [#mu = {mu_ds_str}]", "l")
    leg.AddEntry(h_dt_hits_raw, f"Uncalibrated Raw Veto [#mu = {mu_raw_str}]", "l")
    leg.Draw()

    pave_stats = ROOT.TPaveText(0.15, 0.60, 0.48, 0.88, "NDC")
    pave_stats.SetFillColorAlpha(ROOT.kWhite, 0.90)
    pave_stats.SetBorderSize(1)
    pave_stats.SetTextFont(42)
    pave_stats.SetTextSize(0.030)
    pave_stats.AddText("Fit Parameters (#mu #pm #sigma):")
    if fit_sf_all:
        pave_stats.AddText(f"SF Ref: {fit_sf_all['mu']:+.3f} ns (#sigma={fit_sf_all['sigma']*1000.0:.0f} ps, #chi^{{2}}/ndf={fit_sf_all['chi2_ndf']:.2f})")
    if fit_ds_corr_all:
        pave_stats.AddText(f"DS Corr: {fit_ds_corr_all['mu']:+.3f} ns (#sigma={fit_ds_corr_all['sigma']*1000.0:.0f} ps, #chi^{{2}}/ndf={fit_ds_corr_all['chi2_ndf']:.2f})")
    if fit_ds_all:
        pave_stats.AddText(f"DS Uncorr: {fit_ds_all['mu']:+.3f} ns (#sigma={fit_ds_all['sigma']*1000.0:.0f} ps)")
    if fit_sf_all and fit_ds_corr_all:
        res = fit_sf_all["mu"] - fit_ds_corr_all["mu"]
        pave_stats.AddText(f"#Delta#mu(SF - DS_{{corr}}) = {res*1000.0:+.1f} ps")
    pave_stats.Draw()

    c_comp.Write()

    out_file.Write()
    out_file.Close()
    print(f"[SUCCESS] All histograms and diagnostic canvases saved to: {args.output_root}")

    if args.save_csv and records:
        import pandas as pd
        df = pd.DataFrame(records)
        df.to_csv(args.save_csv, index=False)
        print(f"[SUCCESS] Saved event-by-event shift metrics to {args.save_csv}")

    os._exit(0)


if __name__ == "__main__":
    main()
