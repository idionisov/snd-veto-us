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

  2. Reference Times and Muon Time-of-Flight:
     - SciFi reference time t_0^{SF}: average corrected time of SciFi hits.
     - DS reference time t_0^{DS}: average corrected time of double-sided DS horizontal hits.
     - Muon propagation distance Delta_L = sqrt(Delta_x^2 + Delta_y^2 + Delta_z^2)
       between effective SciFi and DS reference hit positions along the matched track.
     - Expected muon Time-of-Flight: ToF_muon = Delta_L / c_light.

  3. Unified Clock Bridge & Inter-System Time Shift:
     - delta = (t_0^{DS} - t_0^{SF}) - ToF_muon
     - Unified reference time:
         t_ref^{unified} = t_0^{SF} = t_0^{DS} - ToF_muon - delta

Author: Antigravity Assistant / SND@LHC Timing Group
"""

import os
import sys
import math
import argparse
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
        dest="run_number",
        type=int,
        default=5119,
        help="Run number to process (default: 5119)"
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
        default=-1,
        help="Maximum events to process (default: -1 for all events in partition)"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_root",
        type=str,
        default=None,
        help="Path to output ROOT file (default: /eos/user/i/idioniso/Timing/unified_ref_time_run<run>.root)"
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
        "--max-veto-hits",
        dest="max_veto_hits",
        type=int,
        default=4,
        help="Maximum number of valid Veto hits allowed (< 4, default: 4)"
    )
    parser.add_argument(
        "--max-scifi-hits",
        dest="max_scifi_hits",
        type=int,
        default=27,
        help="Maximum number of SciFi hits allowed (< 27, default: 27)"
    )
    parser.add_argument(
        "--max-us-hits",
        dest="max_us_hits",
        type=int,
        default=8,
        help="Maximum number of Upstream hits allowed (< 8, default: 8)"
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


def main():
    args = parse_args()

    # Dynamic default output ROOT file
    if args.output_root is None:
        p_tag = f"_p{args.partition}" if args.partition >= 0 else ""
        args.output_root = f"/eos/user/i/idioniso/Timing/unified_ref_time_run{args.run_number}{p_tag}.root"

    os.makedirs(os.path.dirname(os.path.abspath(args.output_root)), exist_ok=True)

    print("======================================================================")
    print("  SND@LHC Unified Reference Time Bridging: event_ref_time.py")
    print(f"  Run Number        : {args.run_number}")
    print(f"  Partition         : {args.partition}")
    print(f"  Data Base Path    : {args.data_path}")
    print(f"  Output ROOT File  : {args.output_root}")
    print(f"  Track Match Z     : z = {args.match_z:.1f} cm (Window: |Delta x|, |Delta y| <= {args.match_window:.1f} cm)")
    print(f"  Quality Cuts      : chi2/ndf < {args.max_chi2ndf}, slope < {args.max_slope} rad")
    print(f"  Multiplicities    : Veto < {args.max_veto_hits}, SciFi < {args.max_scifi_hits}, US < {args.max_us_hits}, DS < {args.max_ds_hits}")
    print(f"  DeltaT Mode       : {args.delta_t_mode} (Threshold: {args.delta_t_cut} cc)")
    print(f"  Require isIP1     : {args.require_ip1}")
    print(f"  Require StableBm  : {args.require_stable_beams} (Target: {args.beam_mode})")
    print("======================================================================")

    # Resolve geometry file
    if args.geo_file is None:
        from snd import DataManager
        args.geo_file = DataManager.get_geo_path_for_run(args.run_number)
    if not args.geo_file:
        args.geo_file = "/eos/experiment/sndlhc/convertedData/physics/2022/geofile_sndlhc_TI18_V0_2022.root"
    if args.geo_file.startswith("root://eospublic.cern.ch/"):
        args.geo_file = args.geo_file.replace("root://eospublic.cern.ch/", "")

    import Monitor
    import SndlhcTracking
    try:
        import AnalysisFunctions as af
    except ImportError:
        import python.AnalysisFunctions as af

    options = type("Opts", (), {
        "runNumber": args.run_number,
        "path": args.data_path,
        "fname": None,
        "partition": args.partition,
        "server": "",
        "geoFile": "../" + args.geo_file,
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
    out_f = ROOT.TFile.Open(args.output_root, "RECREATE")
    dir_summary = out_f.mkdir("summary")
    dir_matching = out_f.mkdir("track_matching")
    dir_diagnostics = out_f.mkdir("diagnostics")

    # 1. Book Summary Histograms
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
        "Valid SciFi t0",
        "Valid DS t0"
    ]
    for idx, label in enumerate(cut_labels, start=1):
        h_cutflow.GetXaxis().SetBinLabel(idx, label)

    h_tds0 = ROOT.TH1F("h_tds0", "DS Reference Time t_{0}^{DS};t_{0}^{DS} [ns];Events / 0.1 ns", 400, -10.0, 30.0)
    h_tsf0 = ROOT.TH1F("h_tsf0", "SciFi Reference Time t_{0}^{SF};t_{0}^{SF} [ns];Events / 0.1 ns", 400, -20.0, 20.0)
    h_dt_obs = ROOT.TH1F("h_dt_obs", "Observed Reference Time Difference;t_{0}^{DS} - t_{0}^{SF} [ns];Events / 0.1 ns", 400, -10.0, 30.0)
    h_tof = ROOT.TH1F("h_tof_muon", "Expected Muon Time-of-Flight;#Delta L / c [ns];Events / 0.05 ns", 200, 4.0, 14.0)
    h_shift = ROOT.TH1F("h_interSystemShift", "Inter-System Time Shift #delta = (t_{0}^{DS} - t_{0}^{SF}) - ToF_{#mu};#delta [ns];Events / 0.1 ns", 400, -15.0, 15.0)

    # 2. Book Track Matching Histograms
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

    # 3. Book Diagnostics & Correlations
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

    print(f"\n[INFO] Starting event loop over {total_events:,} events...")
    heartbeat = max(5000, total_events // 20)

    prev_event_time = None
    matched_records = []
    pt_a, pt_b = ROOT.TVector3(), ROOT.TVector3()

    for ev_idx in range(total_events):
        if ev_idx > 0 and ev_idx % heartbeat == 0:
            print(f"  Processed {ev_idx:,} / {total_events:,} events (Matched Clean Muons: {len(matched_records):,})...", flush=True)

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
        nVeto = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and h.GetDetectorID() // 10000 == 1)
        nSciFi = len(event.Digi_ScifiHits)
        nUS = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and h.GetDetectorID() // 10000 == 2)
        nDS = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and h.GetDetectorID() // 10000 == 3)

        if nVeto >= args.max_veto_hits or nSciFi >= args.max_scifi_hits or nUS >= args.max_us_hits or nDS >= args.max_ds_hits:
            continue
        h_cutflow.Fill(5)

        # Minimum hits required to form both SciFi and DS tracks
        if nSciFi < 3 or nDS < 2:
            continue

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

        # Fallback to direct event DS hits if track measurements were stripped
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
        h_cutflow.Fill(10) # Valid DS t0

        tds0 = (total_ds[1] + total_ds[2]) / c_tot

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

    print(f"\n[INFO] Finished loop! Clean matched muon events with valid reference times: {len(matched_records):,}")

    # Gaussian fit to inter-system shift distribution
    fit_res = fit_gaussian_iterative(h_shift, n_sigma=2.0)

    # Print Results Summary
    print("\n" + "=" * 70)
    print("  INTER-SYSTEM REFERENCE TIME SHIFT RESULTS")
    print("=" * 70)
    print(f"  Matched Passing Muons : {len(matched_records):,}")
    if fit_res:
        print(f"  Fitted Mean Shift (#delta) : {fit_res['mu']:+.3f} +/- {fit_res['mu_err']:.3f} ns")
        print(f"  Timing Dispersion (#sigma): {fit_res['sigma']*1000.0:.1f} +/- {fit_res['sigma_err']*1000.0:.1f} ps")
        print(f"  Fit Chi2 / NDF            : {fit_res['chi2_ndf']:.2f}")
    else:
        print(f"  Histogram Mean Shift      : {h_shift.GetMean():+.3f} +/- {h_shift.GetMeanError():.3f} ns")
        print(f"  Histogram RMS             : {h_shift.GetRMS()*1000.0:.1f} ps")

    if matched_records:
        shifts_arr = [r["shift"] for r in matched_records]
        tds0_arr = [r["tds0"] for r in matched_records]
        tsf0_arr = [r["tsf0"] for r in matched_records]
        tof_arr = [r["tof_muon"] for r in matched_records]
        print(f"  Mean t_0^{{DS}}             : {np.mean(tds0_arr):+.3f} ns")
        print(f"  Mean t_0^{{SF}}             : {np.mean(tsf0_arr):+.3f} ns")
        print(f"  Mean Observed Delta t     : {np.mean(np.array(tds0_arr) - np.array(tsf0_arr)):+.3f} ns")
        print(f"  Mean Muon ToF             : {np.mean(tof_arr):.3f} ns")
        print("=" * 70)
        print(f"  UNIFIED CLOCK BRIDGE FORMULA:")
        mu_val = fit_res['mu'] if fit_res else np.mean(shifts_arr)
        print(f"    t_ref^{{unified}} = t_0^{{SF}} = t_0^{{DS}} - ToF_muon - ({mu_val:+.3f} ns)")
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
    h_shift.SetStats(False)
    h_shift.GetXaxis().SetTitleOffset(1.15)
    h_shift.GetXaxis().SetTitleSize(0.045)
    h_shift.GetYaxis().SetTitleOffset(1.30)
    h_shift.GetYaxis().SetTitleSize(0.045)
    h_shift.Draw("HIST")

    if fit_res and "func" in fit_res:
        fit_res["func"].Draw("SAME")

    pave = ROOT.TPaveText(0.58, 0.62, 0.89, 0.88, "NDC")
    pave.SetFillColorAlpha(ROOT.kWhite, 0.85)
    pave.SetBorderSize(1)
    pave.SetTextFont(42)
    pave.SetTextSize(0.038)
    pave.AddText(f"Run {args.run_number} (Partition {args.partition})")
    pave.AddText(f"Matched Muons = {len(matched_records):,}")
    if fit_res:
        pave.AddText(f"#mu = {fit_res['mu']:+.3f} #pm {fit_res['mu_err']:.3f} ns")
        pave.AddText(f"#sigma = {fit_res['sigma']*1000.0:.1f} #pm {fit_res['sigma_err']*1000.0:.1f} ps")
        pave.AddText(f"#chi^{{2}} / ndf = {fit_res['chi2_ndf']:.2f}")
    pave.Draw("SAME")
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

    # Write all objects to ROOT file
    out_f.cd()
    c_shift.Write("c_unified_shift")
    c_match.Write("c_track_matching")
    c_overview.Write("c_overview")
    out_f.Write()
    out_f.Close()
    print(f"[INFO] Successfully written ROOT file: {args.output_root}")


if __name__ == "__main__":
    main()
