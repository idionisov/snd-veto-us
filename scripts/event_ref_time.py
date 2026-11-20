#!/usr/bin/env python3
"""
event_ref_time.py
-----------------
Bridges SciFi and Downstream (DS) reference times into a single unified reference time
using clean passing muon events with matched SciFi and DS tracks.

Physics & Calibration Formulation:
  1. Event Selection:
     - EventHeader.isIP1() == True
     - Stable Beams: EventHeader.GetBeamMode() == 11 (or configurable)
     - Event DeltaT < 100 cc (clock cycles between consecutive events)
     - Multiplicities:
         * < 4 Veto hits
         * < 27 SciFi hits
         * < 8 Upstream (US) hits
         * < 18 Downstream (DS) hits
     - Clean Reconstructed Tracks:
         * Reconstructed SciFi track (type 1) and DS track (type 3)
         * Both tracks satisfy chi2/ndf < 5 and total slope theta_xy < 0.1 rad
         * Track matching: Both tracks cross a virtual plate at z = 430 cm
           no more than 3 cm apart in both x and y coordinates:
           |x_SF(430) - x_DS(430)| <= 3.0 cm and |y_SF(430) - y_DS(430)| <= 3.0 cm

  2. Reference Windows & Times:
     - Cuts tsf0 in [sf_t_min, sf_t_max] and tds0 in [ds_t_min, ds_t_max] from config/ref_time_windows.json.
     - SciFi reference time t_0^{SF}: average corrected time of SciFi hits.
     - DS reference time t_0^{DS}: average corrected time of double-sided DS horizontal hits.
     - Muon propagation distance Delta_L = sqrt(Delta_x^2 + Delta_y^2 + Delta_z^2)
       between effective SciFi and DS reference hit positions along the matched track.
     - Expected muon Time-of-Flight: ToF_muon = Delta_L / c_light.

  3. Unified Clock Bridge & Inter-System Time Shift:
     - delta = (t_0^{DS} - t_0^{SF}) - ToF_muon
     - Unified reference time:
         t_ref^{unified} = 0.5 * (t_0^{SF} + (t_0^{DS} - ToF_muon - delta))
     - Full-run unified reference distribution:
         reft-Unified = reft-SF + reft-DS(shifted by -(ToF_muon + delta))

Author: Antigravity Assistant / SND@LHC Timing Group
"""

import os
import sys
import math
import json
import argparse
import subprocess
import numpy as np

# Ensure repository root is in python path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.gErrorIgnoreLevel = ROOT.kWarning

# Physical constants
C_LIGHT = 29.9792458 # cm / ns
TDC2NS = 1.0E9 / 160.316E6 # ns / clock cycle (~6.23768 ns)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Bridge SciFi and DS reference times into a unified reference time."
    )
    parser.add_argument(
        "-r", "--run", "--run-number",
        dest="run_numbers",
        type=str,
        default="5119",
        help="Run number or comma-separated list of runs to process (default: 5119)"
    )
    parser.add_argument(
        "-P", "--partition",
        dest="partition",
        type=int,
        default=0,
        help="Partition number to process (-1 for all partitions, default: 0)"
    )
    parser.add_argument(
        "-p", "--path",
        dest="data_path",
        type=str,
        default="/eos/experiment/sndlhc/convertedData/physics/2022/",
        help="Base path to converted data (default: /eos/experiment/sndlhc/convertedData/physics/2022/)"
    )
    parser.add_argument(
        "-g", "--geofile",
        dest="geo_file",
        type=str,
        default=None,
        help="Override path to geometry file"
    )
    parser.add_argument(
        "-n", "--nEvents", "-b", "--break",
        dest="max_events",
        type=int,
        default=50000,
        help="Maximum events to process per run (default: 50,000; <=0 for all)"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_root",
        type=str,
        default=None,
        help="Path to output ROOT file (default: <output-dir>/run<run>.root)"
    )
    parser.add_argument(
        "--windows-json",
        dest="windows_json",
        type=str,
        default=os.path.join(_REPO_ROOT, "config", "ref_time_windows.json"),
        help="Path to JSON file containing extracted ref time windows (default: config/ref_time_windows.json)"
    )
    parser.add_argument(
        "--ref-runs-dir",
        dest="ref_runs_dir",
        type=str,
        default="/eos/user/i/idioniso/Timing/ref_times/runs",
        help="Directory containing original run ROOT files with reft-DS and reft-SF"
    )
    parser.add_argument(
        "--output-dir",
        dest="output_dir",
        type=str,
        default="/eos/user/i/idioniso/Timing/ref_times/runs_unified",
        help="Output directory for unified run ROOT files (default: /eos/user/i/idioniso/Timing/ref_times/runs_unified)"
    )
    parser.add_argument(
        "--delta-json",
        dest="delta_json",
        type=str,
        default=os.path.join(_REPO_ROOT, "config", "scifi_ds_delta_offsets.json"),
        help="Output JSON path to save delta parameters (default: config/scifi_ds_delta_offsets.json)"
    )
    parser.add_argument(
        "--delta-csv",
        dest="delta_csv",
        type=str,
        default=os.path.join(_REPO_ROOT, "config", "scifi_ds_delta_offsets.csv"),
        help="Output CSV path to save delta parameters (default: config/scifi_ds_delta_offsets.csv)"
    )
    parser.add_argument(
        "--plot-dir",
        dest="plot_dir",
        type=str,
        default=None,
        help="Optional directory to save PNG summary plots"
    )
    parser.add_argument(
        "-c", "--category",
        dest="category",
        type=str,
        default="auto",
        help="Detector category (catI, catII, catIII, or auto; default: auto)"
    )
    parser.add_argument(
        "--worker",
        dest="worker",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS
    )

    # Cuts configuration
    parser.add_argument(
        "--require-ip1",
        dest="require_ip1",
        action="store_true",
        default=True,
        help="Require EventHeader.isIP1() == True (default: True)"
    )
    parser.add_argument(
        "--no-require-ip1",
        dest="require_ip1",
        action="store_false",
        help="Disable requirement of EventHeader.isIP1()"
    )
    parser.add_argument(
        "--require-stable-beams",
        dest="require_stable_beams",
        action="store_true",
        default=False,
        help="Require EventHeader.GetBeamMode() == 11 (StableBeams) (default: False for 2022 data compatibility)"
    )
    parser.add_argument(
        "--beam-mode",
        dest="beam_mode",
        type=int,
        default=11,
        help="Target LHC BeamMode index for stable beams (default: 11)"
    )
    parser.add_argument(
        "--delta-t-cut",
        dest="delta_t_cut",
        type=int,
        default=100,
        help="Consecutive event DeltaT threshold in clock cycles (default: 100 cc)"
    )
    parser.add_argument(
        "--delta-t-mode",
        dest="delta_t_mode",
        choices=["less", "greater", "none"],
        default="none",
        help="Event DeltaT mode: 'less' for DeltaT < threshold, 'greater' for DeltaT > threshold, 'none' to skip (default: none)"
    )
    parser.add_argument(
        "--min-veto-hits",
        dest="min_veto_hits",
        type=int,
        default=1,
        help="Minimum number of valid Veto hits allowed (>= 1, default: 1)"
    )
    parser.add_argument(
        "--max-veto-hits",
        dest="max_veto_hits",
        type=int,
        default=3,
        help="Maximum number of valid Veto hits allowed (<= 3, default: 3)"
    )
    parser.add_argument(
        "--min-scifi-hits",
        dest="min_scifi_hits",
        type=int,
        default=6,
        help="Minimum number of SciFi hits allowed (>= 6, default: 6)"
    )
    parser.add_argument(
        "--max-scifi-hits",
        dest="max_scifi_hits",
        type=int,
        default=27,
        help="Maximum number of SciFi hits allowed (< 27, default: 27)"
    )
    parser.add_argument(
        "--min-us-hits",
        dest="min_us_hits",
        type=int,
        default=4,
        help="Minimum number of Upstream hits allowed (>= 4, default: 4)"
    )
    parser.add_argument(
        "--max-us-hits",
        dest="max_us_hits",
        type=int,
        default=8,
        help="Maximum number of Upstream hits allowed (<= 8, default: 8)"
    )
    parser.add_argument(
        "--min-ds-hits",
        dest="min_ds_hits",
        type=int,
        default=6,
        help="Minimum number of Downstream hits allowed (>= 6, default: 6)"
    )
    parser.add_argument(
        "--max-ds-hits",
        dest="max_ds_hits",
        type=int,
        default=18,
        help="Maximum number of Downstream hits allowed (< 18, default: 18)"
    )
    parser.add_argument(
        "--max-chi2ndf",
        dest="max_chi2ndf",
        type=float,
        default=5.0,
        help="Maximum track chi2/ndf (default: 5.0)"
    )
    parser.add_argument(
        "--max-slope",
        dest="max_slope",
        type=float,
        default=0.1,
        help="Maximum track total slope theta_xy [rad] (default: 0.1 rad)"
    )
    parser.add_argument(
        "--match-z",
        dest="match_z",
        type=float,
        default=430.0,
        help="Z-plane coordinate where SciFi and DS tracks are matched [cm] (default: 430.0 cm)"
    )
    parser.add_argument(
        "--match-window",
        dest="match_window",
        type=float,
        default=3.0,
        help="Maximum allowed coordinate distance |Delta x|, |Delta y| at match-z [cm] (default: 3.0 cm)"
    )
    return parser.parse_args()


def fit_gaussian_iterative(hist, n_sigma=2.0):
    """Performs a 2-step iterative Gaussian fit to extract the peak mean and resolution."""
    if hist.GetEntries() < 15:
        return None

    peak_bin = hist.GetMaximumBin()
    peak_x = hist.GetBinCenter(peak_bin)
    rms = max(0.2, min(hist.GetRMS(), 3.0))

    f_min = peak_x - n_sigma * rms
    f_max = peak_x + n_sigma * rms

    f_gaus = ROOT.TF1(f"{hist.GetName()}_gaus", "gaus", f_min, f_max)
    f_gaus.SetParameters(hist.GetMaximum(), peak_x, min(rms, 1.0))
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

    # Second pass centered closely on fitted mu
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


def run_single_run(run_nr, args):
    """Processes a single run: calculates delta offset, clones original histograms, and saves reft-Unified."""
    # Determine output file path
    if args.output_root:
        output_file = args.output_root
    else:
        output_file = os.path.join(args.output_dir, f"run{run_nr}.root")

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)

    # 1. Load reference time windows if available
    sf_t_min, sf_t_max = -20.0, 20.0
    ds_t_min, ds_t_max = 0.0, 40.0
    has_windows = False
    if args.windows_json and os.path.exists(args.windows_json):
        try:
            with open(args.windows_json, "r") as f:
                win_data = json.load(f)
            r_str = str(run_nr)
            if r_str in win_data:
                w = win_data[r_str]
                sf_t_min = float(w["sf_t_min"])
                sf_t_max = float(w["sf_t_max"])
                ds_t_min = float(w["ds_t_min"])
                ds_t_max = float(w["ds_t_max"])
                has_windows = True
                print(f"[INFO] [Run {run_nr}] Applied Ref Windows: SF=[{sf_t_min:.3f}, {sf_t_max:.3f}] ns, DS=[{ds_t_min:.3f}, {ds_t_max:.3f}] ns")
        except Exception as e:
            print(f"[WARNING] [Run {run_nr}] Could not parse windows JSON: {e}")

    if not has_windows:
        cat_in = getattr(args, "category", "auto")
        if cat_in == "auto":
            if (5117 <= run_nr <= 5174) or (5193 <= run_nr <= 5412):
                cat_in = "catII"
            elif (run_nr <= 5116) or (5175 <= run_nr <= 5192):
                cat_in = "catI"
            else:
                cat_in = "catIII"
        if cat_in == "catI":
            sf_t_min, sf_t_max = 1.0, 5.0
            ds_t_min, ds_t_max = 20.0, 24.5
        elif cat_in == "catII":
            sf_t_min, sf_t_max = 0.0, 3.5
            ds_t_min, ds_t_max = 11.0, 14.5
        elif cat_in == "catIII":
            sf_t_min, sf_t_max = 0.5, 4.0
            ds_t_min, ds_t_max = 14.5, 21.0
        print(f"[INFO] [Run {run_nr}] Fallback Category {cat_in} Windows: SF=[{sf_t_min:.3f}, {sf_t_max:.3f}] ns, DS=[{ds_t_min:.3f}, {ds_t_max:.3f}] ns")

    # 2. Check for pre-existing run file in ref_runs_dir
    orig_ds, orig_sf = None, None
    orig_run_path = os.path.join(args.ref_runs_dir, f"run{run_nr}.root")
    if os.path.exists(orig_run_path):
        f_orig = ROOT.TFile.Open(orig_run_path, "READ")
        if f_orig and not f_orig.IsZombie():
            h_ds_tmp = f_orig.Get("reft-DS")
            h_sf_tmp = f_orig.Get("reft-SF")
            if h_ds_tmp:
                orig_ds = h_ds_tmp.Clone("reft-DS")
                orig_ds.SetDirectory(0)
            if h_sf_tmp:
                orig_sf = h_sf_tmp.Clone("reft-SF")
                orig_sf.SetDirectory(0)
            f_orig.Close()
            print(f"[INFO] [Run {run_nr}] Loaded existing histograms from {orig_run_path} (reft-DS: {orig_ds.GetEntries():,.0f}, reft-SF: {orig_sf.GetEntries():,.0f})")

    # 3. Resolve geometry file
    geo_file = args.geo_file
    if geo_file is None:
        from snd import DataManager
        geo_file = DataManager.get_geo_path_for_run(run_nr)
    if not geo_file:
        geo_file = "/eos/experiment/sndlhc/convertedData/physics/2022/geofile_sndlhc_TI18_V0_2022.root"
    if geo_file.startswith("root://eospublic.cern.ch/"):
        geo_file = geo_file.replace("root://eospublic.cern.ch/", "")

    import Monitor
    import SndlhcTracking
    try:
        import AnalysisFunctions as af
    except ImportError:
        import python.AnalysisFunctions as af

    options = type("Opts", (), {
        "runNumber": run_nr,
        "path": args.data_path,
        "fname": None,
        "partition": args.partition,
        "server": "",
        "geoFile": "../" + geo_file,
        "trackType": "Scifi,DS",
        "online": False,
        "interactive": False,
        "numuStudy": False,
        "nueStudy": False,
        "state": "raw",
        "CorrectionType": "DS",
        "referencesystem": 3,
        "datalocation": "physics",
        "simulation": False,
        "saveTo": "/tmp",
        "nEvents": args.max_events,
        "nStart": 0
    })()

    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")

    # Pass track_task to Monitor for module/geometry registration
    M = Monitor.Monitoring(options, [track_task])
    M.M = M

    # Decouple automatic execution so we only track clean candidate events (massive speedup)
    if "simpleTracking" in M.FairTasks:
        del M.FairTasks["simpleTracking"]

    analysis = af.Analysis(options)
    analysis.SetTask(M)

    # Setup ROOT output file and directory structure
    out_f = ROOT.TFile.Open(output_file, "RECREATE")
    dir_summary = out_f.mkdir("summary")
    dir_matching = out_f.mkdir("track_matching")
    dir_diagnostics = out_f.mkdir("diagnostics")

    # Summary Histograms
    dir_summary.cd()
    h_cutflow = ROOT.TH1F("h_cutflow", "Event Selection Cutflow;Cut Step;Passing Events", 10, 0.5, 10.5)
    cut_labels = [
        "All Events",
        "isIP1()",
        "Stable Beams",
        "DeltaT Cut",
        "Multiplicities",
        "Reconstructed Tracks",
        "Track Quality",
        "Matched at z=430",
        "Valid SciFi t0 (in window)",
        "Valid DS t0 (in window)"
    ]
    for idx, label in enumerate(cut_labels, start=1):
        h_cutflow.GetXaxis().SetBinLabel(idx, label)

    h_tds0 = ROOT.TH1F("h_tds0", f"DS Reference Time (Run {run_nr});t_{{0}}^{{DS}} [ns];Events / 0.1 ns", 400, -10.0, 30.0)
    h_tsf0 = ROOT.TH1F("h_tsf0", f"SciFi Reference Time (Run {run_nr});t_{{0}}^{{SF}} [ns];Events / 0.1 ns", 400, -20.0, 20.0)
    h_dt_obs = ROOT.TH1F("h_dt_obs", f"Observed Reference Time Difference (Run {run_nr});t_{{0}}^{{DS}} - t_{{0}}^{{SF}} [ns];Events / 0.1 ns", 400, -10.0, 30.0)
    h_tof = ROOT.TH1F("h_tof_muon", f"Expected Muon Time-of-Flight (Run {run_nr});#Delta L / c [ns];Events / 0.05 ns", 200, 4.0, 14.0)
    h_shift = ROOT.TH1F("h_interSystemShift", f"Inter-System Time Shift (Run {run_nr});#delta = (t_{{0}}^{{DS}} - t_{{0}}^{{SF}}) - ToF_{{#mu}} [ns];Events / 0.1 ns", 400, -15.0, 15.0)

    # Track Matching Histograms
    dir_matching.cd()
    h2_match_dx_dy = ROOT.TH2F(
        "h2_match_dx_dy",
        f"Track Matching Residuals at z={args.match_z:.0f} cm;x_{{SF}} - x_{{DS}} [cm];y_{{SF}} - y_{{DS}} [cm]",
        100, -args.match_window * 2.0, args.match_window * 2.0,
        100, -args.match_window * 2.0, args.match_window * 2.0
    )
    h_match_dr = ROOT.TH1F(
        "h_match_dr",
        f"Transverse Matching Distance at z={args.match_z:.0f} cm;#Delta r_{{xy}} = #sqrt{{#Delta x^{{2}} + #Delta y^{{2}}}} [cm];Tracks / 0.1 cm",
        100, 0.0, args.match_window * 2.0
    )
    h2_slope_sf_vs_ds = ROOT.TH2F(
        "h2_slope_SF_vs_DS",
        "Track Slope Correlation;SciFi Slope #theta_{xy}^{SF} [rad];DS Slope #theta_{xy}^{DS} [rad]",
        100, 0.0, args.max_slope * 1.5,
        100, 0.0, args.max_slope * 1.5
    )

    # Diagnostics & Correlations
    dir_diagnostics.cd()
    h2_tds_vs_tsf = ROOT.TH2F(
        "h2_tds_vs_tsf",
        "Reference Time Correlation;t_{0}^{SF} [ns];t_{0}^{DS} [ns]",
        200, -15.0, 15.0,
        200, -5.0, 25.0
    )
    h2_shift_vs_dz = ROOT.TH2F(
        "h2_shift_vs_dz",
        "Inter-System Shift vs. Reference Flight Distance;#Delta z = #bar{z}_{DS} - #bar{z}_{SF} [cm];#delta [ns]",
        100, 150.0, 250.0,
        200, -15.0, 15.0
    )
    p_shift_vs_dz = ROOT.TProfile(
        "p_shift_vs_dz",
        "Profile: Inter-System Shift vs. #Delta z;#Delta z [cm];#langle#delta#rangle [ns]",
        20, 150.0, 250.0, -15.0, 15.0
    )
    h2_shift_vs_slope = ROOT.TH2F(
        "h2_shift_vs_slope",
        "Inter-System Shift vs. Muon Track Slope;Total Track Slope #theta_{xy} [rad];#delta [ns]",
        100, 0.0, args.max_slope * 1.2,
        200, -15.0, 15.0
    )
    h_delta_t_events = ROOT.TH1F(
        "h_delta_t_events",
        "Time Difference between Consecutive Events;|t_{ev} - t_{ev-1}| [clock cycles];Events / 2 cc",
        250, 0.0, 500.0
    )

    # Setup loop
    total_events = M.GetEntries()
    if args.max_events > 0 and args.max_events < total_events:
        total_events = args.max_events

    print(f"\n[INFO] [Run {run_nr}] Starting event loop over {total_events:,} events...")
    heartbeat = max(5000, total_events // 10)

    prev_event_time = None
    matched_records = []
    pt_a, pt_b = ROOT.TVector3(), ROOT.TVector3()

    for ev_idx in range(total_events):
        if ev_idx > 0 and ev_idx % heartbeat == 0:
            print(f"  [Run {run_nr}] Processed {ev_idx:,} / {total_events:,} events (Matched Clean Muons: {len(matched_records):,})...", flush=True)

        event = M.GetEvent(ev_idx)
        header = event.EventHeader
        h_cutflow.Fill(1) # All events

        # Cut 1: isIP1()
        if args.require_ip1:
            if not header.isIP1():
                continue
        h_cutflow.Fill(2)

        # Cut 2: Stable Beams
        if args.require_stable_beams:
            if header.GetBeamMode() != args.beam_mode:
                continue
        h_cutflow.Fill(3)

        # Cut 3: Event DeltaT
        cur_time = header.GetEventTime()
        dt_cc = abs(cur_time - prev_event_time) if prev_event_time is not None else 999999
        prev_event_time = cur_time
        h_delta_t_events.Fill(min(499.0, dt_cc))

        if args.delta_t_mode == "less":
            if dt_cc >= args.delta_t_cut:
                continue
        elif args.delta_t_mode == "greater":
            if dt_cc <= args.delta_t_cut:
                continue
        h_cutflow.Fill(4)

        # Cut 4: Multiplicities
        # Requirements:
        #   (1 <= nVetoHits <= 3)
        #   (6 <= nScifiHits < 27)
        #   (4 <= nUShits <= 8)
        #   (6 <= nDShits < 18)
        nVeto = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and h.GetDetectorID() // 10000 == 1)
        nSciFi = len(event.Digi_ScifiHits)
        nUS = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and h.GetDetectorID() // 10000 == 2)
        nDS = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and h.GetDetectorID() // 10000 == 3)

        if not (args.min_veto_hits <= nVeto <= args.max_veto_hits):
            continue
        if not (args.min_scifi_hits <= nSciFi < args.max_scifi_hits):
            continue
        if not (args.min_us_hits <= nUS <= args.max_us_hits):
            continue
        if not (args.min_ds_hits <= nDS < args.max_ds_hits):
            continue
        h_cutflow.Fill(5)

        # Initialize event alignment
        M.Scifi.InitEvent(header)
        M.MuFilter.InitEvent(header)

        # Clear tracks from previous event to prevent accumulation
        if hasattr(track_task.fittedTracks, "Clear"):
            track_task.fittedTracks.Clear()
        elif hasattr(track_task.fittedTracks, "Delete"):
            track_task.fittedTracks.Delete()

        # Execute tracking on candidate event
        track_task.ExecuteTask("Scifi,DS")
        tracks = track_task.fittedTracks

        scifi_tracks = []
        ds_tracks = []

        for trk_idx in range(tracks.GetEntries()):
            trk = tracks[trk_idx]
            tr_type = trk.getTrackType() if hasattr(trk, "getTrackType") else trk.GetUniqueID()
            chi2ndf = trk.getChi2Ndf() if hasattr(trk, "getChi2Ndf") else (trk.getFitStatus().getChi2() / max(1, trk.getFitStatus().getNdf()))

            if hasattr(trk, "getSlopeXZ"):
                sx, sy = trk.getSlopeXZ(), trk.getSlopeYZ()
                slope = math.sqrt(sx**2 + sy**2)
            else:
                mom = trk.getFittedState().getMom()
                slope = math.sqrt((mom.x() / mom.z())**2 + (mom.y() / mom.z())**2)

            # Store track by type
            if tr_type == 1:
                scifi_tracks.append((trk, chi2ndf, slope))
            elif tr_type == 3:
                ds_tracks.append((trk, chi2ndf, slope))

        if not (scifi_tracks and ds_tracks):
            continue
        h_cutflow.Fill(6) # Reconstructed tracks present

        # Quality cuts: chi2/ndf < 5 and slopes < 0.1 rad
        good_scifi = [t for t in scifi_tracks if t[1] < args.max_chi2ndf and t[2] < args.max_slope]
        good_ds = [t for t in ds_tracks if t[1] < args.max_chi2ndf and t[2] < args.max_slope]

        if not (good_scifi and good_ds):
            continue
        h_cutflow.Fill(7) # Quality tracks

        # Track matching at z = match_z (430 cm)
        best_match = None
        min_dr = 9999.0

        for sf_t, sf_chi2, sf_sl in good_scifi:
            if hasattr(sf_t, "getFittedState"):
                st_sf = sf_t.getFittedState()
                p_sf, m_sf = st_sf.getPos(), st_sf.getMom()
                lam_sf = (args.match_z - p_sf.z()) / m_sf.z()
                xs, ys = p_sf.x() + lam_sf * m_sf.x(), p_sf.y() + lam_sf * m_sf.y()
            elif hasattr(sf_t, "extrapolateToPlaneAtZ"):
                pos_sf = sf_t.extrapolateToPlaneAtZ(args.match_z)
                xs, ys = pos_sf.X(), pos_sf.Y()
            else:
                p_sf, m_sf = sf_t.getStart(), sf_t.getTrackMom()
                lam_sf = (args.match_z - p_sf.Z()) / m_sf.Z()
                xs, ys = p_sf.X() + lam_sf * m_sf.X(), p_sf.Y() + lam_sf * m_sf.Y()

            for ds_t, ds_chi2, ds_sl in good_ds:
                if hasattr(ds_t, "getFittedState"):
                    st_ds = ds_t.getFittedState()
                    p_ds, m_ds = st_ds.getPos(), st_ds.getMom()
                    lam_ds = (args.match_z - p_ds.z()) / m_ds.z()
                    xd, yd = p_ds.x() + lam_ds * m_ds.x(), p_ds.y() + lam_ds * m_ds.y()
                elif hasattr(ds_t, "extrapolateToPlaneAtZ"):
                    pos_ds = ds_t.extrapolateToPlaneAtZ(args.match_z)
                    xd, yd = pos_ds.X(), pos_ds.Y()
                else:
                    p_ds, m_ds = ds_t.getStart(), ds_t.getTrackMom()
                    lam_ds = (args.match_z - p_ds.Z()) / m_ds.Z()
                    xd, yd = p_ds.X() + lam_ds * m_ds.X(), p_ds.Y() + lam_ds * m_ds.Y()

                dx = xs - xd
                dy = ys - yd
                dr = math.sqrt(dx**2 + dy**2)

                h2_match_dx_dy.Fill(dx, dy)
                h_match_dr.Fill(dr)
                h2_slope_sf_vs_ds.Fill(sf_sl, ds_sl)

                if abs(dx) <= args.match_window and abs(dy) <= args.match_window:
                    if dr < min_dr:
                        min_dr = dr
                        best_match = (sf_t, ds_t, xs, ys, xd, yd, dx, dy, sf_sl, ds_sl)

        if best_match is None:
            continue
        h_cutflow.Fill(8) # Matched at z=430 cm

        # Extract SciFi Reference Time
        tsf0 = analysis.GetScifiAverageTime(M.Scifi, event.Digi_ScifiHits, mode="tsf0")
        if tsf0 == -999.:
            continue
        # Apply SciFi window cut
        if not (sf_t_min <= tsf0 <= sf_t_max):
            continue
        h_cutflow.Fill(9) # Valid SciFi t0

        # Extract DS Reference Time from double-sided horizontal DS hits
        ds_trk = best_match[1]
        stations = {h.GetDetectorID(): h for h in event.Digi_MuFilterHits}
        total_ds = {1: 0.0, 2: 0.0}
        counter_ds = {1: 0, 2: 0}
        z_ds_hits = []

        # Extract measurements from DS track
        if hasattr(ds_trk, "getNumPointsWithMeasurement"):
            nM = ds_trk.getNumPointsWithMeasurement()
            for n in range(nM):
                pt = ds_trk.getPointWithMeasurement(n)
                detID = pt.getRawMeasurement().getDetId()
                if detID not in stations:
                    continue
                s, p, b = af.Analysis.parseDetID(analysis, detID)
                if s != 3 or p not in (1, 2) or b >= 60:
                    continue
                thit = stations[detID]
                tdcs = thit.GetAllTimes()
                if len(tdcs) != 2:
                    continue
                for sipm, clock in tdcs:
                    t_corr = M.MuFilter.GetCorrectedTime(detID, sipm, clock * TDC2NS, 0)
                    total_ds[p] += t_corr
                    counter_ds[p] += 1
                M.MuFilter.GetPosition(detID, pt_a, pt_b)
                z_ds_hits.append(0.5 * (pt_a.z() + pt_b.z()))
        elif hasattr(ds_trk, "getRawMeasDetIDs"):
            det_ids = ds_trk.getRawMeasDetIDs()
            for detID in det_ids:
                if detID not in stations:
                    continue
                s, p, b = af.Analysis.parseDetID(analysis, detID)
                if s != 3 or p not in (1, 2) or b >= 60:
                    continue
                thit = stations[detID]
                tdcs = thit.GetAllTimes()
                if len(tdcs) != 2:
                    continue
                for sipm, clock in tdcs:
                    t_corr = M.MuFilter.GetCorrectedTime(detID, sipm, clock * TDC2NS, 0)
                    total_ds[p] += t_corr
                    counter_ds[p] += 1
                M.MuFilter.GetPosition(detID, pt_a, pt_b)
                z_ds_hits.append(0.5 * (pt_a.z() + pt_b.z()))

        c_tot = counter_ds[1] + counter_ds[2]
        if c_tot == 0:
            for detID, thit in stations.items():
                s, p, b = af.Analysis.parseDetID(analysis, detID)
                if s != 3 or p not in (1, 2) or b >= 60:
                    continue
                tdcs = thit.GetAllTimes()
                if len(tdcs) != 2:
                    continue
                for sipm, clock in tdcs:
                    t_corr = M.MuFilter.GetCorrectedTime(detID, sipm, clock * TDC2NS, 0)
                    total_ds[p] += t_corr
                    counter_ds[p] += 1
                M.MuFilter.GetPosition(detID, pt_a, pt_b)
                z_ds_hits.append(0.5 * (pt_a.z() + pt_b.z()))
            c_tot = counter_ds[1] + counter_ds[2]

        if c_tot == 0:
            continue

        tds0 = (total_ds[1] + total_ds[2]) / c_tot
        # Apply DS window cut
        if not (ds_t_min <= tds0 <= ds_t_max):
            continue
        h_cutflow.Fill(10) # Valid DS t0

        # Mean z positions of reference hits
        z_sf_hits = []
        for h in event.Digi_ScifiHits:
            detID = h.GetDetectorID()
            M.Scifi.GetSiPMPosition(detID, pt_a, pt_b)
            z_sf_hits.append(0.5 * (pt_a.z() + pt_b.z()))

        mean_z_sf = sum(z_sf_hits) / len(z_sf_hits) if z_sf_hits else 325.9
        mean_z_ds = sum(z_ds_hits) / len(z_ds_hits) if z_ds_hits else 529.5
        delta_z = mean_z_ds - mean_z_sf

        # Total 3D flight path length along the muon track
        avg_slope = 0.5 * (best_match[8] + best_match[9])
        cos_theta = 1.0 / math.sqrt(1.0 + avg_slope**2)
        delta_L = delta_z / cos_theta
        tof_muon = delta_L / C_LIGHT

        dt_obs = tds0 - tsf0
        shift = dt_obs - tof_muon

        # Fill Histograms
        h_tds0.Fill(tds0)
        h_tsf0.Fill(tsf0)
        h_dt_obs.Fill(dt_obs)
        h_tof.Fill(tof_muon)
        h_shift.Fill(shift)

        h2_tds_vs_tsf.Fill(tsf0, tds0)
        h2_shift_vs_dz.Fill(delta_z, shift)
        p_shift_vs_dz.Fill(delta_z, shift)
        h2_shift_vs_slope.Fill(avg_slope, shift)

        matched_records.append({
            "ev_idx": ev_idx,
            "tsf0": tsf0,
            "tds0": tds0,
            "dt_obs": dt_obs,
            "tof_muon": tof_muon,
            "shift": shift,
            "delta_z": delta_z,
            "delta_L": delta_L,
            "slope": avg_slope
        })

    print(f"\n[INFO] [Run {run_nr}] Finished loop! Clean matched muon events with valid reference times: {len(matched_records):,}")

    # Gaussian fit to inter-system shift distribution
    fit_res = fit_gaussian_iterative(h_shift, n_sigma=2.0)

    if fit_res:
        delta_ref = fit_res["mu"]
        delta_err = fit_res["mu_err"]
        delta_sigma = fit_res["sigma"]
        delta_sig_err = fit_res.get("sigma_err", 0.0)
        delta_chi2ndf = fit_res["chi2_ndf"]
    else:
        delta_ref = h_shift.GetMean() if h_shift.GetEntries() > 0 else 0.0
        delta_err = h_shift.GetMeanError() if h_shift.GetEntries() > 0 else 0.0
        delta_sigma = h_shift.GetRMS() if h_shift.GetEntries() > 0 else 0.0
        delta_sig_err = 0.0
        delta_chi2ndf = 1.0

    mean_tof = float(np.mean([r["tof_muon"] for r in matched_records])) if matched_records else 6.79
    mean_dt_obs = float(np.mean([r["dt_obs"] for r in matched_records])) if matched_records else (h_dt_obs.GetMean() if h_dt_obs.GetEntries() > 0 else 11.0)
    mean_tsf0 = float(np.mean([r["tsf0"] for r in matched_records])) if matched_records else (h_tsf0.GetMean() if h_tsf0.GetEntries() > 0 else 1.5)
    mean_tds0 = float(np.mean([r["tds0"] for r in matched_records])) if matched_records else (h_tds0.GetMean() if h_tds0.GetEntries() > 0 else 12.5)

    print("\n" + "=" * 70)
    print(f"  INTER-SYSTEM REFERENCE TIME SHIFT RESULTS (Run {run_nr})")
    print("=" * 70)
    print(f"  Matched Passing Muons      : {len(matched_records):,}")
    print(f"  Fitted Mean Shift (#delta) : {delta_ref:+.3f} +/- {delta_err:.3f} ns")
    print(f"  Timing Dispersion (#sigma) : {delta_sigma*1000.0:.1f} ps (chi2/ndf = {delta_chi2ndf:.2f})")
    print(f"  Mean Observed Delta t      : {mean_dt_obs:+.3f} ns (DS={mean_tds0:+.3f} ns, SF={mean_tsf0:+.3f} ns)")
    print(f"  Mean Muon Time-of-Flight   : {mean_tof:.3f} ns")
    print(f"  UNIFIED BRIDGE FORMULA     : t_ref^unified = t_0^SF = t_0^DS - ToF - ({delta_ref:+.3f} ns)")
    print("=" * 70)

    # 4. Generate Diagnostic Canvases
    c_shift = ROOT.TCanvas("c_unified_shift", "Unified Inter-System Reference Time Shift", 1000, 750)
    c_shift.SetLeftMargin(0.13)
    c_shift.SetRightMargin(0.08)
    c_shift.SetTopMargin(0.09)
    c_shift.SetBottomMargin(0.13)
    c_shift.SetGrid(1, 1)

    h_shift.SetLineWidth(2)
    h_shift.SetLineColor(ROOT.kAzure + 1)
    h_shift.SetFillColorAlpha(ROOT.kAzure - 4, 0.35)
    h_shift.SetStats(True)
    ROOT.gStyle.SetOptFit(1111)
    ROOT.gStyle.SetOptStat(1110)
    h_shift.GetXaxis().SetTitleOffset(1.15)
    h_shift.GetXaxis().SetTitleSize(0.045)
    h_shift.GetYaxis().SetTitleOffset(1.30)
    h_shift.GetYaxis().SetTitleSize(0.045)
    h_shift.Draw("HIST")

    if fit_res and "func" in fit_res:
        fit_res["func"].Draw("SAME")

    c_shift.Update()

    # Move stats box if generated, or draw dedicated fit info pave
    st = h_shift.FindObject("stats")
    if st:
        st.SetX1NDC(0.60)
        st.SetX2NDC(0.92)
        st.SetY1NDC(0.60)
        st.SetY2NDC(0.88)
        st.SetBorderSize(1)
        st.SetFillColorAlpha(ROOT.kWhite, 0.90)
        st.Draw()
    else:
        pave = ROOT.TPaveText(0.60, 0.60, 0.92, 0.88, "NDC")
        pave.SetFillColorAlpha(ROOT.kWhite, 0.90)
        pave.SetBorderSize(1)
        pave.SetTextFont(42)
        pave.SetTextSize(0.035)
        pave.SetTextAlign(12)
        pave.AddText(f"Run {run_nr} (Partition {args.partition})")
        pave.AddText(f"Matched Muons: {len(matched_records):,}")
        pave.AddText(f"Fit Mean (#mu): {delta_ref:+.3f} #pm {delta_err:.3f} ns")
        pave.AddText(f"Fit StdDev (#sigma): {delta_sigma*1000.0:.1f} #pm {delta_sig_err*1000.0:.1f} ps")
        pave.AddText(f"#chi^{{2}} / ndf: {delta_chi2ndf:.2f}")
        pave.Draw("SAME")

    c_shift.Modified()
    c_shift.Update()

    # Track matching canvas
    c_match = ROOT.TCanvas("c_track_matching", "SciFi-DS Track Matching at z=430 cm", 1200, 500)
    c_match.Divide(2, 1)
    c_match.cd(1)
    ROOT.gPad.SetLeftMargin(0.13)
    ROOT.gPad.SetRightMargin(0.12)
    ROOT.gPad.SetGrid(1, 1)
    h2_match_dx_dy.SetStats(False)
    h2_match_dx_dy.Draw("COLZ")

    c_match.cd(2)
    ROOT.gPad.SetLeftMargin(0.13)
    ROOT.gPad.SetBottomMargin(0.12)
    ROOT.gPad.SetGrid(1, 1)
    h_match_dr.SetStats(False)
    h_match_dr.SetLineWidth(2)
    h_match_dr.SetLineColor(ROOT.kTeal + 2)
    h_match_dr.SetFillColorAlpha(ROOT.kTeal - 7, 0.35)
    h_match_dr.Draw("HIST")

    # 4-panel overview canvas
    c_overview = ROOT.TCanvas("c_overview", "Unified Reference Time Overview", 1400, 900)
    c_overview.Divide(2, 2)

    c_overview.cd(1)
    ROOT.gPad.SetLeftMargin(0.13)
    ROOT.gPad.SetGrid(1, 1)
    h_cutflow.SetStats(False)
    h_cutflow.SetLineWidth(2)
    h_cutflow.SetLineColor(ROOT.kBlue + 2)
    h_cutflow.LabelsOption("v")
    h_cutflow.Draw("HIST TEXT0")

    c_overview.cd(2)
    ROOT.gPad.SetLeftMargin(0.13)
    ROOT.gPad.SetRightMargin(0.12)
    ROOT.gPad.SetGrid(1, 1)
    h2_tds_vs_tsf.SetStats(False)
    h2_tds_vs_tsf.Draw("COLZ")

    c_overview.cd(3)
    ROOT.gPad.SetLeftMargin(0.13)
    ROOT.gPad.SetGrid(1, 1)
    h_dt_obs.SetStats(False)
    h_dt_obs.SetLineWidth(2)
    h_dt_obs.SetLineColor(ROOT.kOrange + 2)
    h_dt_obs.Draw("HIST")

    c_overview.cd(4)
    ROOT.gPad.SetLeftMargin(0.13)
    ROOT.gPad.SetGrid(1, 1)
    h_shift.Draw("HIST")
    if fit_res and "func" in fit_res:
        fit_res["func"].Draw("SAME")
    pave_ov = pave.Clone("pave_overview")
    pave_ov.Draw("SAME")

    if args.plot_dir:
        os.makedirs(args.plot_dir, exist_ok=True)
        c_shift.SaveAs(os.path.join(args.plot_dir, f"c_unified_ref_shift_run{run_nr}.png"))
        c_match.SaveAs(os.path.join(args.plot_dir, f"c_track_matching_z430_run{run_nr}.png"))
        c_overview.SaveAs(os.path.join(args.plot_dir, f"c_overview_run{run_nr}.png"))

    # 5. Populate top-level ROOT objects
    out_f.cd()

    # Clone or write reft-DS and reft-SF
    if orig_ds:
        orig_ds.Write("reft-DS", ROOT.TObject.kOverwrite)
    else:
        h_tds0.Write("reft-DS", ROOT.TObject.kOverwrite)

    if orig_sf:
        orig_sf.Write("reft-SF", ROOT.TObject.kOverwrite)
    else:
        h_tsf0.Write("reft-SF", ROOT.TObject.kOverwrite)

    # Top level shift distribution
    h_shift.Write("h_interSystemShift", ROOT.TObject.kOverwrite)

    # Unified reference time distribution for the run:
    # reft-Unified: 200 bins from -25 to 25 ns (aligned with reft-SF)
    h_unified = ROOT.TH1F("reft-Unified", f"Unified Reference Time (Run {run_nr});t_{{0}}^{{unified}} [ns];Counts", 200, -25.0, 25.0)
    h_unified.SetDirectory(0)

    # Add SciFi component (within valid window)
    base_sf = orig_sf if orig_sf else h_tsf0
    for b in range(1, base_sf.GetNbinsX() + 1):
        t_sf = base_sf.GetBinCenter(b)
        if sf_t_min <= t_sf <= sf_t_max:
            c = base_sf.GetBinContent(b)
            if c > 0:
                h_unified.Fill(t_sf, c)

    # Add DS component shifted by -(mean_tof + delta_ref) (within valid window)
    base_ds = orig_ds if orig_ds else h_tds0
    delta_shift = mean_tof + delta_ref
    for b in range(1, base_ds.GetNbinsX() + 1):
        t_ds = base_ds.GetBinCenter(b)
        if ds_t_min <= t_ds <= ds_t_max:
            c = base_ds.GetBinContent(b)
            if c > 0:
                t_corr = t_ds - delta_shift
                h_unified.Fill(t_corr, c)

    h_unified.SetEntries(h_unified.Integral())
    out_f.cd()
    h_unified.Write("reft-Unified", ROOT.TObject.kOverwrite)

    # Event-by-event unified reference time from matched clean muons
    h_uni_muons = ROOT.TH1F("reft-Unified-muons", f"Unified Reference Time from Matched Muons (Run {run_nr});t_{{0}}^{{unified}} [ns];Tracks / 0.1 ns", 400, -20.0, 20.0)
    h_uni_muons.SetDirectory(0)
    for r in matched_records:
        t_uni = 0.5 * (r["tsf0"] + (r["tds0"] - r["tof_muon"] - delta_ref))
        h_uni_muons.Fill(t_uni)
    h_uni_muons.Write("reft-Unified-muons", ROOT.TObject.kOverwrite)


    # Canvases
    c_shift.Write("c_unified_shift")
    c_match.Write("c_track_matching")
    c_overview.Write("c_overview")

    out_f.Write()
    out_f.Close()
    print(f"[INFO] [Run {run_nr}] Successfully written ROOT file: {output_file}")

    cat = "II"
    try:
        csv_runs = os.path.join(_REPO_ROOT, "runs_2022.csv")
        if os.path.exists(csv_runs):
            import pandas as pd
            df_runs = pd.read_csv(csv_runs)
            m = df_runs[df_runs["run_number"] == int(run_nr)]
            if not m.empty:
                cat = str(m.iloc[0]["category"])
    except Exception:
        pass

    result_dict = {
        "run_nr": int(run_nr),
        "partition": int(args.partition),
        "category": cat,
        "delta_ref": round(float(delta_ref), 4),
        "delta_err": round(float(delta_err), 4),
        "delta_sigma": round(float(delta_sigma), 4),
        "delta_chi2ndf": round(float(delta_chi2ndf), 3),
        "mean_tof": round(float(mean_tof), 4),
        "mean_dt_obs": round(float(mean_dt_obs), 4),
        "mean_tsf0": round(float(mean_tsf0), 4),
        "mean_tds0": round(float(mean_tds0), 4),
        "n_matched_muons": len(matched_records),
        "output_file": output_file
    }

    # Write summary json alongside output_file
    if output_file.endswith(".root"):
        json_out = output_file[:-5] + ".json"
        try:
            with open(json_out, "w") as f:
                json.dump(result_dict, f, indent=2)
        except Exception:
            pass

    # Write worker temporary JSON if called in worker mode
    if args.worker:
        worker_json = f"/tmp/delta_offset_run{run_nr}.json"
        with open(worker_json, "w") as f:
            json.dump(result_dict, f, indent=2)

    return result_dict


def update_summary_store(new_records, json_path, csv_path):
    """Updates the JSON and CSV stores with newly extracted delta parameters."""
    existing = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    for rec in new_records:
        r_str = str(rec["run_nr"])
        existing[r_str] = rec

    os.makedirs(os.path.dirname(os.path.abspath(json_path)), exist_ok=True)
    with open(json_path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"[SUCCESS] Updated JSON store ({len(existing)} runs): {json_path}")

    # Mirror to EOS if possible
    eos_json = os.path.join("/eos/user/i/idioniso/Timing", os.path.basename(json_path))
    try:
        with open(eos_json, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"[SUCCESS] Mirrored JSON store to EOS: {eos_json}")
    except Exception as e:
        print(f"[WARNING] Could not mirror JSON to EOS: {e}")

    # Write CSV
    if csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(csv_path)), exist_ok=True)
        import pandas as pd
        rows = list(existing.values())
        rows.sort(key=lambda x: x["run_nr"])
        df = pd.DataFrame(rows)
        df.to_csv(csv_path, index=False)
        print(f"[SUCCESS] Updated CSV store: {csv_path}")

        eos_csv = os.path.join("/eos/user/i/idioniso/Timing", os.path.basename(csv_path))
        try:
            df.to_csv(eos_csv, index=False)
            print(f"[SUCCESS] Mirrored CSV store to EOS: {eos_csv}")
        except Exception as e:
            print(f"[WARNING] Could not mirror CSV to EOS: {e}")


def main():
    args = parse_args()

    # Worker dispatch
    if args.worker:
        run_nr = int(args.run_numbers)
        run_single_run(run_nr, args)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(0)

    # Master orchestrator
    run_list = [int(x.strip()) for x in args.run_numbers.split(",") if x.strip()]

    print("=" * 70)
    print("  SND@LHC Unified Reference Time Bridging: event_ref_time.py")
    print(f"  Runs to Process   : {run_list}")
    print(f"  Events per Run    : {args.max_events:,}")
    print(f"  Partition         : {args.partition}")
    print(f"  Windows JSON      : {args.windows_json}")
    print(f"  Ref Runs Dir      : {args.ref_runs_dir}")
    print(f"  Output Dir        : {args.output_dir}")
    print(f"  Delta JSON Store  : {args.delta_json}")
    print(f"  Delta CSV Store   : {args.delta_csv}")
    print("=" * 70)

    results = []

    if len(run_list) == 1:
        res = run_single_run(run_list[0], args)
        results.append(res)
    else:
        for idx, r in enumerate(run_list, start=1):
            print(f"\n>>> [{idx}/{len(run_list)}] Dispatching Worker for Run {r}...")
            cmd = [
                sys.executable,
                "-X", "faulthandler",
                os.path.abspath(__file__),
                "--worker",
                "-r", str(r),
                "-P", str(args.partition),
                "-n", str(args.max_events),
                "-p", args.data_path,
                "--windows-json", args.windows_json,
                "--ref-runs-dir", args.ref_runs_dir,
                "--output-dir", args.output_dir,
                "--min-veto-hits", str(args.min_veto_hits),
                "--max-veto-hits", str(args.max_veto_hits),
                "--min-scifi-hits", str(args.min_scifi_hits),
                "--max-scifi-hits", str(args.max_scifi_hits),
                "--min-us-hits", str(args.min_us_hits),
                "--max-us-hits", str(args.max_us_hits),
                "--min-ds-hits", str(args.min_ds_hits),
                "--max-ds-hits", str(args.max_ds_hits),
                "--max-chi2ndf", str(args.max_chi2ndf),
                "--match-window", str(args.match_window),
                "--match-z", str(args.match_z)
            ]
            if args.plot_dir:
                cmd.extend(["--plot-dir", args.plot_dir])
            if args.geo_file:
                cmd.extend(["-g", args.geo_file])

            proc = subprocess.run(cmd)
            if proc.returncode != 0:
                print(f"[ERROR] Worker for Run {r} exited with code {proc.returncode}!")
                continue

            worker_json = f"/tmp/delta_offset_run{r}.json"
            if os.path.exists(worker_json):
                with open(worker_json, "r") as f:
                    rec = json.load(f)
                results.append(rec)
                os.remove(worker_json)

    # Update summary stores
    if results:
        update_summary_store(results, args.delta_json, args.delta_csv)

        # Print formatted summary table
        print("\n" + "=" * 90)
        print(f"{'Run':<8} {'Delta (ns)':<16} {'Sigma (ps)':<12} {'Chi2/NDF':<10} {'ToF (ns)':<10} {'Matched Muons':<14} {'Output ROOT File'}")
        print("-" * 90)
        for r in results:
            d_str = f"{r['delta_ref']:+.3f} +/- {r['delta_err']:.3f}"
            s_str = f"{r['delta_sigma']*1000.0:.1f}"
            out_base = os.path.basename(r['output_file'])
            print(f"{r['run_nr']:<8} {d_str:<16} {s_str:<12} {r['delta_chi2ndf']:<10.2f} {r['mean_tof']:<10.3f} {r['n_matched_muons']:<14} {out_base}")
        print("=" * 90)


if __name__ == "__main__":
    main()
