#!/usr/bin/env python3
"""
sipm_timewalk.py
----------------
Extracts the Time-Walk curves (dt vs QDC) for each SiPM in the Upstream systems:
  dt = t0^DS - t_ToF_corrected

For each SiPM, produces two 2D histograms (dt vs QDC):
  1. Specific c_scint: ToF correction uses c_scint measured specifically for that SiPM and run.
  2. Unified c_scint: ToF correction uses the run-averaged c_scint across all SiPMs of that run.

Propagation correction logic (following AnalysisFunctions.py / TimeWalk.py):
  MuFilter.GetPosition(detID, A, B)
  xref = 0.5 * (A.x() + B.x())
  t_raw = clock * TDC2ns
  ToF_correction = (x_pred - xref) / c_scint
  If sipm < 8: t_ToF = t_raw + ToF_correction
  Else:        t_ToF = t_raw - ToF_correction
  dt = t0 - t_ToF

Prerequisite:
  c_scint constants from JSON file for the run:
  - Default search paths:
    /eos/user/i/idioniso/Timing/cscint/runs/fits/run<RUN>_cscint.json
    /eos/user/i/idioniso/Timing/run<RUN>/run<RUN>_timing_calibration.json

Output ROOT File Structure:
  <catI | catII | catIII>/runXXXX/<detID_SiPM>/
    ├── dtvqdc_specific   (dt vs QDC using channel-specific c_scint)
    └── dtvqdc_unified    (dt vs QDC using run-averaged c_scint)
"""

import os
import sys
import glob
import json
import argparse
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


def get_run_category(run_nr):
    """Determines category (catI, catII, catIII) based on run number."""
    if run_nr <= 5116 or (5175 <= run_nr <= 5192):
        return "catI"
    elif (5117 <= run_nr <= 5174) or (5193 <= run_nr <= 5412):
        return "catII"
    else:
        return "catIII"


def get_tds0_window(run_nr):
    """Returns (tds0_min, tds0_max) window for the given run."""
    cat = get_run_category(run_nr)
    if cat == "catI":
        if run_nr <= 4819:
            return 14.0, 17.5
        elif run_nr <= 5116:
            return 16.5, 20.0
        elif 5175 <= run_nr <= 5192:
            return 5.5, 9.0
        return 14.0, 17.5
    elif cat == "catII":
        return 11.0, 16.0
    else:
        return 11.0, 23.5


def get_tsf0_window(run_nr=None):
    """Returns (tsf0_min, tsf0_max) window for SciFi reference time."""
    return -0.5, 6.0


def load_run_cscint(run_nr: int, cscint_file: str = None, placeholder_cscint: float = 13.25, force_placeholder: bool = False):
    """
    Loads c_scint constants for the given run.
    If force_placeholder=True or no precomputed file exists, falls back to placeholder_cscint (default: 13.25 cm/ns).
    Returns:
      (cscint_specific_dict, cscint_unified_val)
      where cscint_specific_dict maps "<detID_sipm>" -> c_scint
    """
    if force_placeholder or (cscint_file and cscint_file.lower() in ("placeholder", "none", "dummy")):
        print(f"[INFO] Using placeholder c_scint: {placeholder_cscint:.2f} +/- 1.15 cm/ns (forced placeholder mode)", flush=True)
        return {}, float(placeholder_cscint)

    candidates = []
    if cscint_file:
        candidates.append(cscint_file)

    candidates.extend([
        f"/eos/user/i/idioniso/Timing/cscint/runs/fits/run{run_nr}_cscint.json",
        f"/eos/user/i/idioniso/Timing/cscint/runs/fits/run{run_nr:06d}_cscint.json",
        f"/eos/user/i/idioniso/Timing/cscint/fits/run{run_nr}_cscint.json",
        f"/eos/user/i/idioniso/Timing/run{run_nr:06d}/run{run_nr:06d}_timing_calibration.json",
        f"/eos/user/i/idioniso/Timing/run{run_nr}/run{run_nr}_timing_calibration.json",
    ])

    loaded_path = None
    data = None
    for pth in candidates:
        if os.path.exists(pth):
            try:
                with open(pth) as f:
                    data = json.load(f)
                loaded_path = pth
                break
            except Exception:
                continue

    if not data:
        print(f"[INFO] No precomputed c_scint file found for run {run_nr}. Using placeholder: {placeholder_cscint:.2f} +/- 1.15 cm/ns", flush=True)
        return {}, float(placeholder_cscint)

    print(f"[INFO] Loaded c_scint constants from: {loaded_path}", flush=True)

    specific_map = {}
    if "DS" in data and isinstance(data["DS"], dict):
        for k, v in data["DS"].items():
            if isinstance(v, dict) and "c_scint" in v:
                specific_map[k] = float(v["c_scint"])
            elif isinstance(v, list) and len(v) >= 1:
                specific_map[k] = float(v[0])
            elif isinstance(v, (float, int)):
                specific_map[k] = float(v)
    elif "MuFilter" in data and "cscint" in data["MuFilter"]:
        for k, v in data["MuFilter"]["cscint"].items():
            specific_map[k] = float(v[0]) if isinstance(v, list) else float(v)

    vals = [v for v in specific_map.values() if 5.0 < v < 30.0]
    unified_c = float(np.median(vals)) if vals else float(placeholder_cscint)

    return specific_map, unified_c


def run_worker(run_nr, partition, out_file, cscint_file=None, placeholder_cscint=13.25, force_placeholder=False, max_events=0):
    """Processes a single partition file to produce Time-Walk 2D histograms."""
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.gErrorIgnoreLevel = ROOT.kError

    import SndlhcGeo
    import AnalysisFunctions as af
    import SndlhcTracking
    import Monitor

    # Resolve raw data path
    if run_nr < 5413:
        raw_pattern = f"/eos/experiment/sndlhc/convertedData/physics/2022/run_{run_nr:06d}/sndsw_raw-{partition:04d}.root"
    else:
        matches = glob.glob(f"/eos/experiment/sndlhc/convertedData/physics/*/run_{run_nr:06d}/sndsw_raw-{partition:04d}.root")
        if not matches:
            matches = glob.glob(f"/eos/experiment/sndlhc/convertedData/physics/*/run_*/run_{run_nr:06d}/sndsw_raw-{partition:04d}.root")
        raw_pattern = matches[0] if matches else ""

    if not raw_pattern or not os.path.exists(raw_pattern):
        raise FileNotFoundError(f"Partition raw file not found for run {run_nr}, partition {partition}")

    # Load c_scint constants
    specific_cscint, unified_cscint = load_run_cscint(
        run_nr, cscint_file, placeholder_cscint=placeholder_cscint, force_placeholder=force_placeholder
    )

    # Load geometry
    geo_file = "/eos/experiment/sndlhc/convertedData/physics/2022/geofile_sndlhc_TI18_V0_2022.root"
    if run_nr >= 5413:
        alt_geo = glob.glob(f"/eos/experiment/sndlhc/convertedData/physics/*/geofile_sndlhc_*.root")
        if alt_geo:
            geo_file = alt_geo[-1]

    geo_file_opt = "../" + geo_file

    data_base_dir = os.path.dirname(os.path.dirname(raw_pattern))
    if not data_base_dir.endswith("/"):
        data_base_dir += "/"

    options = type("Options", (), {
        "runNumber": run_nr,
        "numuStudy": False,
        "nueStudy": False,
        "state": "raw",
        "CorrectionType": "DS",
        "referencesystem": 3,
        "datalocation": "physics",
        "simulation": False,
        "geoFile": geo_file_opt,
        "path": data_base_dir,
        "server": "",
        "online": False,
        "fname": None,
        "partition": partition,
        "interactive": False,
        "saveTo": "/tmp",
        "nStart": 0,
        "nEvents": max_events,
        "trackType": "ScifiDS",
        "fastTrackingFilter": (run_nr >= 5431),
    })()

    analysis = af.Analysis(options)
    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")
    FairTasks = [track_task]
    M = Monitor.Monitoring(options, FairTasks)
    M.M = M
    analysis.SetTask(M)

    # Optimize tree branch reading: activate only needed detector branches
    if hasattr(M, "eventTree") and M.eventTree:
        M.eventTree.SetBranchStatus("*", 0)
        for b in ("EventHeader*", "Digi_MuFilterHits*", "Digi_ScifiHits*"):
            M.eventTree.SetBranchStatus(b, 1)

    nav = ROOT.gGeoManager.GetCurrentNavigator()
    mu_filter = M.MuFilter
    tdc2ns = analysis.TDC2ns
    tds0_min, tds0_max = get_tds0_window(run_nr)
    category = get_run_category(run_nr)

    # Monkey-patch GetDSHaverage for safe DS horizontal time calculation
    orig_GetDSHaverage = af.Analysis.GetDSHaverage

    def safe_GetDSHaverage(self, hits, mode="tds0"):
        if mode == "tds0":
            stations = {i.GetDetectorID(): i for i in hits}
            total = {i: 0 for i in range(4)}
            counter = {i: 0 for i in range(4)}

            theTrack = getattr(self, "current_ds_track", None)
            if theTrack is None:
                for trk in self.task.M.Reco_MuonTracks:
                    tt = trk.getTrackType() if hasattr(trk, "getTrackType") else trk.GetUniqueID()
                    if tt == 3:
                        theTrack = trk
                        break
            if theTrack is None:
                return -999.

            nM = theTrack.getNumPointsWithMeasurement()

            for n in range(nM):
                pt = theTrack.getPointWithMeasurement(n)
                W = pt.getRawMeasurement()
                detID = W.getDetId()
                if detID not in stations:
                    continue
                s, p, b = self.parseDetID(detID)
                if s != 3:
                    continue
                trackHit = stations[detID]
                tdcs = trackHit.GetAllTimes()
                if not all([p in (0, 1, 2), b < 60, len(tdcs) == 2]):
                    continue

                for item in tdcs:
                    SiPM, clock = item
                    dscorrectedtime = self.task.M.MuFilter.GetCorrectedTime(detID, SiPM, clock * self.TDC2ns, 0)
                    total[p] += dscorrectedtime
                    counter[p] += 1

            sum_total = total[1] + total[2]
            counter_total = counter[1] + counter[2]
            if counter_total == 0:
                return -999.
            return sum_total / counter_total, counter_total

        return orig_GetDSHaverage(self, hits, mode=mode)

    af.Analysis.GetDSHaverage = safe_GetDSHaverage

    n_entries = M.GetEntries()
    if max_events > 0:
        n_entries = min(n_entries, max_events)

    print(f" ~ Run {run_nr}, Partition {partition}: Processing {n_entries:,} events...", flush=True)

    # Initialize 2D histograms (QDC vs dt)
    hists_specific = {}
    hists_unified = {}

    def get_or_create_hist(ch_key, mode_str="specific"):
        if mode_str == "specific":
            if ch_key not in hists_specific:
                h = ROOT.TH2F(
                    f"dtvqdc_specific_{ch_key}",
                    f"Time-Walk ({ch_key}) specific c_scint;QDC_{{SiPM}} [a.u.];t_{{0}}^{{DS}} - t_{{ToF}} [ns]",
                    100, 0, 200, 175, -10, 25
                )
                h.SetDirectory(0)
                hists_specific[ch_key] = h
            return hists_specific[ch_key]
        else:
            if ch_key not in hists_unified:
                h = ROOT.TH2F(
                    f"dtvqdc_unified_{ch_key}",
                    f"Time-Walk ({ch_key}) unified c_scint;QDC_{{SiPM}} [a.u.];t_{{0}}^{{DS}} - t_{{ToF}} [ns]",
                    100, 0, 200, 175, -10, 25
                )
                h.SetDirectory(0)
                hists_unified[ch_key] = h
            return hists_unified[ch_key]

    # Pre-cache bar central positions (xref)
    bar_xref = {}
    pt_a = ROOT.TVector3()
    pt_b = ROOT.TVector3()

    def get_bar_xref(det_id):
        if det_id not in bar_xref:
            mu_filter.GetPosition(det_id, pt_a, pt_b)
            bar_xref[det_id] = 0.5 * (pt_a.x() + pt_b.x())
        return bar_xref[det_id]

    # Event loop
    for i in range(n_entries):
        M.GetEvent(i)
        event = M.eventTree

        tracks = getattr(M, "Reco_MuonTracks", None)
        if not tracks or len(tracks) == 0:
            continue

        best_ds = None
        for trk in tracks:
            fit_status = trk.getFitStatus()
            if not fit_status or not fit_status.isFitConverged() or fit_status.getNdf() == 0:
                continue
            chi2ndf = fit_status.getChi2() / fit_status.getNdf()
            if chi2ndf >= 5.0:
                continue

            fitted_state = trk.getFittedState()
            mom = fitted_state.getMom()
            pos = fitted_state.getPos()
            if mom.z() == 0:
                continue

            slope_x = mom.x() / mom.z()
            slope_y = mom.y() / mom.z()
            if abs(slope_x) >= 0.1 or abs(slope_y) >= 0.1:
                continue

            trk_type = trk.getTrackType() if hasattr(trk, "getTrackType") else trk.GetUniqueID()
            if trk_type == 3:
                if best_ds is None or chi2ndf < best_ds["chi2ndf"]:
                    best_ds = {"pos": pos, "mom": mom, "chi2ndf": chi2ndf, "track": trk}

        if not best_ds:
            continue

        analysis.current_ds_track = best_ds["track"]

        # DS reference time
        tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
        tds0_val = None
        if isinstance(tds0, (tuple, list)):
            if tds0[0] != -999.: tds0_val = tds0[0]
        elif tds0 != -999.:
            tds0_val = tds0

        if tds0_val is None or not (tds0_min <= tds0_val <= tds0_max):
            continue

        # Predict crossed US bars
        pos_ds = best_ds["pos"]
        mom_ds = best_ds["mom"]
        expected_us_bars = {}
        for plane in range(5):
            z_key = 20 + plane
            if z_key not in M.zPos["MuFilter"]: continue
            zEx = M.zPos["MuFilter"][z_key]
            lam = (zEx - pos_ds.z()) / mom_ds.z()
            xEx = pos_ds.x() + lam * mom_ds.x()
            yEx = pos_ds.y() + lam * mom_ds.y()
            node = nav.FindNode(xEx, yEx, zEx)
            if node and node.GetName().startswith("volMuUpstreamBar_"):
                try:
                    bar_id = int(node.GetName().split("_")[-1])
                    expected_us_bars[plane] = (bar_id, xEx)
                except ValueError:
                    pass

        if not expected_us_bars:
            continue

        # Loop over hits
        for hit in event.Digi_MuFilterHits:
            if not hit.isValid(): continue
            detID = hit.GetDetectorID()
            s, p, b = analysis.parseDetID(detID)
            if s != 2: continue

            if p not in expected_us_bars or expected_us_bars[p][0] != detID:
                continue
            x_pred = expected_us_bars[p][1]
            xref = get_bar_xref(detID)

            channels_t = hit.GetAllTimes()
            signals_dict = dict(hit.GetAllSignals())

            for sipm_num, clock in channels_t:
                if sipm_num < 0 or sipm_num > 15: continue
                if analysis.IsSmallSiPMchannel(sipm_num): continue
                ch_key = f"{detID}_{sipm_num}"
                if ch_key == "21005_15": continue

                qdc = signals_dict.get(sipm_num, None)
                if qdc is None or qdc <= 0: continue

                t_raw = clock * tdc2ns
                sign = 1.0 if sipm_num < 8 else -1.0

                # 1. Channel-specific c_scint
                c_spec = specific_cscint.get(ch_key, unified_cscint)
                if c_spec > 0:
                    tof_spec = (x_pred - xref) / c_spec
                    t_tof_spec = t_raw + sign * tof_spec
                    dt_spec = tds0_val - t_tof_spec
                    h_spec = get_or_create_hist(ch_key, "specific")
                    h_spec.Fill(qdc, dt_spec)

                # 2. Run-unified c_scint
                if unified_cscint > 0:
                    tof_uni = (x_pred - xref) / unified_cscint
                    t_tof_uni = t_raw + sign * tof_uni
                    dt_uni = tds0_val - t_tof_uni
                    h_uni = get_or_create_hist(ch_key, "unified")
                    h_uni.Fill(qdc, dt_uni)

    # Save to output ROOT file
    os.makedirs(os.path.dirname(os.path.abspath(out_file)), exist_ok=True)
    fout = ROOT.TFile.Open(out_file, "RECREATE")

    cat_dir = fout.mkdir(category)
    run_dir = cat_dir.mkdir(f"run{run_nr:06d}")

    all_keys = sorted(set(list(hists_specific.keys()) + list(hists_unified.keys())))
    for ch in all_keys:
        d = run_dir.mkdir(ch)
        d.cd()
        if ch in hists_specific:
            hists_specific[ch].Write("dtvqdc_specific")
        if ch in hists_unified:
            hists_unified[ch].Write("dtvqdc_unified")

    fout.Close()
    print(f"[SUCCESS] Partition completed: saved {len(all_keys)} SiPM channels to {out_file}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Extract Time-Walk 2D histograms (dt vs QDC) per partition.")
    parser.add_argument("-r", "--run", type=int, required=True, help="Run number")
    parser.add_argument("-P", "--partition", type=int, required=True, help="Partition number")
    parser.add_argument("-o", "--output", type=str, required=True, help="Output ROOT file")
    parser.add_argument("-c", "--cscint", type=str, default=None, help="Path to c_scint constants JSON")
    parser.add_argument("--placeholder-cscint", "--cscint-val", dest="placeholder_cscint", type=float, default=13.25,
                        help="Placeholder c_scint value [cm/ns] (default: 13.25 +/- 1.15 cm/ns)")
    parser.add_argument("--force-placeholder", action="store_true",
                        help="Force using placeholder c_scint even if JSON calibration exists")
    parser.add_argument("-n", "--max-events", type=int, default=0, help="Max events to process (0 = all)")
    args = parser.parse_args()

    run_worker(
        run_nr=args.run,
        partition=args.partition,
        out_file=args.output,
        cscint_file=args.cscint,
        placeholder_cscint=args.placeholder_cscint,
        force_placeholder=args.force_placeholder,
        max_events=args.max_events
    )


if __name__ == "__main__":
    main()
