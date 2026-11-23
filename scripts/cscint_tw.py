#!/usr/bin/env python3
"""
cscint_tw.py
------------
Extracts the difference between reference times and SiPM readout time:
  dt^DS = t0^DS - t_SiPM^TW  and  dt^SF = t0^SF - t_SiPM^TW
for each channel (detectorID_SiPMnum: XXXXX_Y) in the Veto, Upstream, and Downstream systems,
incorporating channel-specific Time-Walk corrections:
  t_SiPM^TW = t_SiPM + Delta t^TW(Q)
  dt^TW = (t0 - t_SiPM) - Delta t^TW(Q)
where Delta t^TW(Q) = alpha / (beta * Q - Q0) + gamma * Q

Time-walk calibration parameters are loaded per-channel from:
  /eos/user/i/idioniso/Timing/timewalk/fits/run<RUN>_timing_calibration.json

Selection logic (matching mufilter_cscint.py & timewalk.py):
  - Upstream bars (system 2, detID 20000..24009):
      ALWAYS crossed by a qualified DS track (reconstructed DS track,
      chi2ndf < 5, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad).
  - Veto bars (system 1, detID 10000..11006):
      ALWAYS crossed by a qualified SciFi track (reconstructed SciFi track,
      chi2ndf < 5, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad).
  - Downstream bars (system 3):
      ALWAYS crossed by a qualified DS track.

Reference time cuts:
  - t0^DS: Category-dependent window cut from config/ref_time_windows.json
  - t0^SF: Category-dependent window cut (-0.5 <= t0^SF <= 6.0 ns)

Output ROOT File Structure:
  <catI | catII | catIII>/runXXXX/<detID_SiPM>/
    ├── dt-DS   (t0^DS - t_SiPM^TW vs position)
    └── dt-SF   (t0^SF - t_SiPM^TW vs position)
"""

import os
import sys
import json
import tempfile
import argparse
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_DEFAULT_WINDOWS_JSON = os.path.join(_REPO_ROOT, "config", "ref_time_windows.json")
_DEFAULT_TIMEWALK_DIR = "/eos/user/i/idioniso/Timing/timewalk/fits"
_WINDOWS_CACHE = None


def get_ref_windows_cache(json_path=None):
    global _WINDOWS_CACHE
    if _WINDOWS_CACHE is None:
        target = json_path or _DEFAULT_WINDOWS_JSON
        if not os.path.exists(target):
            candidate = os.path.join(_REPO_ROOT, "config", "ref_time_windows.json")
            if os.path.exists(candidate):
                target = candidate
        if os.path.exists(target):
            try:
                with open(target, "r") as f:
                    _WINDOWS_CACHE = json.load(f)
            except Exception as e:
                print(f"[WARNING] Could not load reference windows from {target}: {e}", file=sys.stderr)
                _WINDOWS_CACHE = {}
        else:
            _WINDOWS_CACHE = {}
    return _WINDOWS_CACHE


def get_run_category(run_nr):
    """Determines category (catI, catII, catIII) based on run number."""
    if run_nr <= 5116 or (5175 <= run_nr <= 5192):
        return "catI"
    elif (5117 <= run_nr <= 5174) or (5193 <= run_nr <= 5412):
        return "catII"
    else:
        return "catIII"


def get_tds0_window(run_nr, json_path=None):
    """Returns (tds0_min, tds0_max) window for the given run."""
    windows = get_ref_windows_cache(json_path)
    win = windows.get(str(run_nr))
    if win and win.get("ds_t_min") is not None and win.get("ds_t_max") is not None:
        return float(win["ds_t_min"]), float(win["ds_t_max"])

    # Fallback to category-based window if run not in JSON
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


def get_tsf0_window(run_nr=None, json_path=None):
    """Returns (tsf0_min, tsf0_max) window for SciFi reference time."""
    if run_nr is not None:
        windows = get_ref_windows_cache(json_path)
        win = windows.get(str(run_nr))
        if win and win.get("sf_t_min") is not None and win.get("sf_t_max") is not None:
            return float(win["sf_t_min"]), float(win["sf_t_max"])
    return -0.5, 6.0


def load_run_timewalk(run_nr: int, tw_file: str = None, tw_dir: str = _DEFAULT_TIMEWALK_DIR):
    """
    Loads channel-specific and run-level fallback time-walk calibration parameters from JSON.
    Returns:
      tw_params: {'DS': {ch: {'alpha': ..., 'beta': ..., 'qdc0': ..., 'gamma': ...}}, 'SF': {...}}
      tw_summary: {'DS': summary_dict, 'SF': summary_dict}
    """
    candidates = []
    if tw_file and os.path.exists(tw_file):
        candidates.append(tw_file)
    if tw_dir:
        candidates.extend([
            os.path.join(tw_dir, f"run{run_nr}_timing_calibration.json"),
            os.path.join(tw_dir, f"run{run_nr:06d}_timing_calibration.json"),
            os.path.join(tw_dir, f"run_{run_nr}_timing_calibration.json"),
        ])
    cat = get_run_category(run_nr)
    if tw_dir:
        candidates.append(os.path.join(tw_dir, f"{cat}_timing_calibration.json"))

    loaded_path = None
    data = None
    for pth in candidates:
        if os.path.exists(pth):
            try:
                with open(pth, "r") as f:
                    data = json.load(f)
                loaded_path = pth
                break
            except Exception:
                continue

    tw_params = {"DS": {}, "SF": {}}
    tw_summary = {"DS": {}, "SF": {}}

    if not data:
        print(f"[WARNING] [Run {run_nr}] No timewalk calibration file found. Proceeding uncorrected (shift=0.0).", flush=True)
        return tw_params, tw_summary

    tw_all = data.get("timewalk", {})
    summary_all = data.get("summary", {})

    for ref in ("DS", "SF"):
        ref_tw = tw_all.get(ref, {})
        for ch_k, pdict in ref_tw.items():
            if isinstance(pdict, dict) and "alpha" in pdict:
                tw_params[ref][ch_k] = pdict
        if ref in summary_all:
            tw_summary[ref] = summary_all[ref]

    print(f"Loaded timewalk constants from {loaded_path}: DS={len(tw_params['DS'])} channels, SF={len(tw_params['SF'])} channels.", flush=True)
    return tw_params, tw_summary


def get_tw_shift(tw_dict, ref, ch_key, qdc, summary_dict=None):
    """
    Computes time-walk shift: shift = alpha / (beta * Q - Q0) + gamma * Q.
    dt_corrected = dt_raw - shift.
    """
    ref_dict = tw_dict.get(ref, {})
    ch_params = ref_dict.get(ch_key)

    if ch_params and "alpha" in ch_params and ch_params["alpha"] is not None:
        alpha = float(ch_params.get("alpha", 0.0))
        beta = float(ch_params.get("beta", 1.0))
        qdc0 = float(ch_params.get("qdc0", 0.0))
        gamma = float(ch_params.get("gamma", 0.0))
    elif summary_dict and ref in summary_dict:
        sum_ref = summary_dict[ref]
        alpha = float(sum_ref.get("median_alpha", 0.0))
        beta = float(sum_ref.get("median_beta", 1.0))
        qdc0 = float(sum_ref.get("median_qdc0", 0.0))
        gamma = float(sum_ref.get("median_gamma", 0.0))
    else:
        return 0.0

    denom = beta * qdc - qdc0
    if denom <= 1e-4:
        denom = 1e-4
    return (alpha / denom) + gamma * qdc


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract t0^DS - t_SiPM^TW and t0^SF - t_SiPM^TW distributions with Time-Walk corrections for each SiPM channel."
    )
    parser.add_argument(
        "-r", "--run", "--run-number",
        dest="run_number",
        type=str,
        default=None,
        help="Run number or comma-separated list of runs to process"
    )
    parser.add_argument(
        "-b", "--break", "--break-events", "-n",
        dest="break_events",
        type=int,
        default=0,
        help="Break processing if processed events exceed this number (default: 0 = full run)"
    )
    parser.add_argument(
        "-j", "--threads", "--jobs", "--workers",
        dest="n_workers",
        type=int,
        default=10,
        help="Number of parallel worker processes / threads (default: 10)"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        type=str,
        default="/eos/user/i/idioniso/Timing/cscint_tw_2022.root",
        help="Single output ROOT file storing cat/run/detectorID_SiPM directories"
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=str,
        default="/afs/cern.ch/work/i/idioniso/snd-veto-us/runs_2022.csv",
        help="Path to runs catalog CSV"
    )
    parser.add_argument(
        "-P", "--partition",
        dest="partition",
        type=int,
        default=-1,
        help="Data partition number (default: -1 for all partitions)"
    )
    parser.add_argument(
        "-g", "--geofile",
        dest="geo_file",
        type=str,
        default=None,
        help="Optional override for geometry file"
    )
    parser.add_argument(
        "-f", "--force",
        dest="force",
        action="store_true",
        default=False,
        help="Force reprocessing of runs already present in output file"
    )
    parser.add_argument(
        "--windows-json",
        dest="windows_json",
        type=str,
        default=_DEFAULT_WINDOWS_JSON,
        help="Path to precalculated reference windows JSON (default: config/ref_time_windows.json)"
    )
    parser.add_argument(
        "--timewalk-dir",
        dest="timewalk_dir",
        type=str,
        default=_DEFAULT_TIMEWALK_DIR,
        help=f"Directory containing run*_timing_calibration.json (default: {_DEFAULT_TIMEWALK_DIR})"
    )
    parser.add_argument(
        "--timewalk-file",
        dest="timewalk_file",
        type=str,
        default=None,
        help="Optional direct path override for time-walk calibration JSON"
    )
    parser.add_argument(
        "--no-veto-scifi1", "--no-veto-scifi",
        dest="require_veto_scifi1",
        action="store_false",
        default=True,
        help="Disable requirement of at least one Veto hit or SciFi station 1 hit per event"
    )
    # Internal worker flags
    parser.add_argument(
        "--worker",
        dest="worker",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS
    )
    parser.add_argument(
        "--temp-output",
        dest="temp_output",
        type=str,
        default=None,
        help=argparse.SUPPRESS
    )
    return parser.parse_args()


def run_worker(run_nr, break_events, temp_output, partition=-1, geo_file_override=None,
               windows_json=None, timewalk_dir=_DEFAULT_TIMEWALK_DIR, timewalk_file=None,
               require_veto_scifi1=True):
    """Processes a single run partition in an isolated subprocess with time-walk correction."""
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.PyConfig.IgnoreCommandLineOptions = True

    import Monitor
    import SndlhcTracking
    try:
        import AnalysisFunctions as af
    except ImportError:
        import python.AnalysisFunctions as af
    from snd import DataManager

    # 1. Resolve dataset and geometry paths via DataManager
    data_path = DataManager.get_data_base_path(run_nr)
    if not data_path:
        raise RuntimeError(f"Could not resolve data base path for run {run_nr}")

    if geo_file_override:
        geo_file = geo_file_override
    else:
        geo_file = DataManager.get_geo_path_for_run(run_nr)
    if not geo_file:
        raise RuntimeError(f"Could not resolve geometry file for run {run_nr}")

    # 2. Configure server and paths
    server = os.environ.get("EOSSHIP", "root://eospublic.cern.ch/")
    if not server.endswith("/"):
        server += "/"

    if data_path.startswith(server):
        data_path = data_path[len(server):]
    elif data_path.startswith("root://eospublic.cern.ch/"):
        data_path = data_path[len("root://eospublic.cern.ch/"):]

    if geo_file.startswith(server) or geo_file.startswith("root://"):
        geo_file_opt = "../" + geo_file
    else:
        geo_file_opt = geo_file

    max_ev = break_events if (break_events is not None and break_events > 0) else -1
    save_to_dir = os.path.dirname(os.path.abspath(temp_output)) if temp_output else "/tmp"

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
        "path": data_path,
        "server": server,
        "online": False,
        "fname": None,
        "partition": partition,
        "interactive": False,
        "saveTo": save_to_dir,
        "nStart": 0,
        "nEvents": max_ev,
        "trackType": "ScifiDS",
    })()

    analysis = af.Analysis(options)

    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")
    FairTasks = [track_task]
    M = Monitor.Monitoring(options, FairTasks)
    M.M = M
    analysis.SetTask(M)

    # Pre-fetch geometry references
    nav = ROOT.gGeoManager.GetCurrentNavigator()
    mu_filter = M.MuFilter
    tdc2ns = analysis.TDC2ns
    tds0_min, tds0_max = get_tds0_window(run_nr, windows_json)
    tsf0_min, tsf0_max = get_tsf0_window(run_nr, windows_json)
    category = get_run_category(run_nr)

    # Load time-walk calibration constants
    tw_params, tw_summary = load_run_timewalk(run_nr, tw_file=timewalk_file, tw_dir=timewalk_dir)

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
                    tt = trk.getTrackType() if hasattr(trk, 'getTrackType') else trk.GetUniqueID()
                    if tt == 3:
                        theTrack = trk
                        break
            if theTrack is None:
                return -999.

            nM = theTrack.getNumPointsWithMeasurement()

            for n in range(nM):
                pt = theTrack.getPointWithMeasurement(n)
                raw_m = pt.getRawMeasurement()
                detID = raw_m.getDetId()
                if detID not in stations:
                    continue
                s, p, b = self.parseDetID(detID)
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

    # Pre-calculate plane Z positions for Veto, US, and DS dynamically from geometry
    a_tmp, b_tmp = ROOT.TVector3(), ROOT.TVector3()
    veto_z_planes = {}
    n_veto_planes = M.systemAndPlanes.get(1, 2)
    for pl in range(n_veto_planes):
        mu_filter.GetPosition(10000 + pl * 1000, a_tmp, b_tmp)
        veto_z_planes[pl] = (a_tmp.z() + b_tmp.z()) / 2.0

    us_z_planes = {}
    n_us_planes = M.systemAndPlanes.get(2, 5)
    for pl in range(n_us_planes):
        mu_filter.GetPosition(20000 + pl * 1000, a_tmp, b_tmp)
        us_z_planes[pl] = (a_tmp.z() + b_tmp.z()) / 2.0

    ds_z_planes = {}
    for st in range(4):
        if st < 3:
            mu_filter.GetPosition(30000 + st * 1000, a_tmp, b_tmp)
            ds_z_planes[(st, "hor")] = (a_tmp.z() + b_tmp.z()) / 2.0
        mu_filter.GetPosition(30000 + st * 1000 + 60, a_tmp, b_tmp)
        ds_z_planes[(st, "ver")] = (a_tmp.z() + b_tmp.z()) / 2.0

    # Histogram cache: channel_key -> {'dt-DS': TH2F, 'dt-SF': TH2F}
    hist_cache = {}

    def get_hist(channel_key, hist_type):
        if channel_key not in hist_cache:
            hist_cache[channel_key] = {}
        if hist_type not in hist_cache[channel_key]:
            det_id = int(channel_key.split("_")[0])
            subsys, pl, bar = analysis.parseDetID(det_id)

            if subsys == 1:
                if pl >= 2:
                    pos_name = "y"
                    nbins_pos, pos_min, pos_max = 50, 10.0, 60.0
                else:
                    pos_name = "x"
                    nbins_pos, pos_min, pos_max = 46, -53.0, -7.0
            elif subsys == 2:
                pos_name = "x"
                nbins_pos, pos_min, pos_max = 60, -60.0, 0.0
            elif subsys == 3:
                if bar >= 60:
                    pos_name = "y"
                    nbins_pos, pos_min, pos_max = 60, 8.0, 68.0
                else:
                    pos_name = "x"
                    nbins_pos, pos_min, pos_max = 65, -65.0, 0.0
            else:
                pos_name = "x"
                nbins_pos, pos_min, pos_max = 60, -60.0, 0.0

            nbins_dt, dt_min, dt_max = 220, -27.5, 27.5

            if hist_type == "dt-DS":
                title = f"{channel_key} t_{{0}}^{{DS}} - t_{{SiPM}}^{{TW}} vs {pos_name}-position (Run {run_nr});{pos_name}_{{predicted}} [cm];t_{{0}}^{{DS}} - t_{{SiPM}}^{{TW}} [ns]"
                h = ROOT.TH2F(f"dt-DS_{channel_key}", title, nbins_pos, pos_min, pos_max, nbins_dt, dt_min, dt_max)
            else:
                title = f"{channel_key} t_{{0}}^{{SF}} - t_{{SiPM}}^{{TW}} vs {pos_name}-position (Run {run_nr});{pos_name}_{{predicted}} [cm];t_{{0}}^{{SF}} - t_{{SiPM}}^{{TW}} [ns]"
                h = ROOT.TH2F(f"dt-SF_{channel_key}", title, nbins_pos, pos_min, pos_max, nbins_dt, dt_min, dt_max)
            h.SetDirectory(0)
            hist_cache[channel_key][hist_type] = h
        return hist_cache[channel_key][hist_type]

    actual_entries = M.GetEntries()
    events_to_process = min(max_ev, actual_entries) if max_ev > 0 else actual_entries

    print(
        f" ~ Processing Run {run_nr} ({category}): {events_to_process:,} events "
        f"[t0^DS cut: {tds0_min:.2f} <= t0^DS <= {tds0_max:.2f} ns, "
        f"t0^SF cut: {tsf0_min:.2f} <= t0^SF <= {tsf0_max:.2f} ns]",
        flush=True
    )

    heartbeat = 50000

    def passes_fiducial(det_id, x_ex, y_ex):
        a_pt, b_pt = ROOT.TVector3(), ROOT.TVector3()
        mu_filter.GetPosition(det_id, a_pt, b_pt)
        subsys, pl, bar = analysis.parseDetID(det_id)
        is_vertical = (subsys == 1 and pl >= 2) or (subsys == 3 and bar >= 60)
        cut = 2.0 if is_vertical else 5.0
        if is_vertical:
            return (min(a_pt.y(), b_pt.y()) + cut) <= y_ex <= (max(a_pt.y(), b_pt.y()) - cut)
        else:
            return (min(a_pt.x(), b_pt.x()) + cut) <= x_ex <= (max(a_pt.x(), b_pt.x()) - cut)

    for n in range(events_to_process):
        if n > 0 and n % heartbeat == 0:
            print(f"   [Run {run_nr}] Processed {n:,} / {events_to_process:,} events...", flush=True)

        event = M.GetEvent(n)

        # Bunch Crossing selection: only accept colliding IP1 bunches for LHC synchronous runs
        if analysis.isLHCsynch(run_nr):
            if hasattr(M, "xing") and isinstance(M.xing, dict) and not M.xing.get("IP1", True):
                continue

        # Require at least one Veto hit OR at least one SciFi hit in station 1
        if require_veto_scifi1:
            has_veto = any(h.isValid() and (h.GetDetectorID() // 10000 == 1) for h in event.Digi_MuFilterHits)
            has_scifi1 = any(h.isValid() and (h.GetStation() == 1 if hasattr(h, "GetStation") else h.GetDetectorID() // 1000000 == 1) for h in event.Digi_ScifiHits)
            if not (has_veto or has_scifi1):
                continue

        # 1. Select qualified tracks
        qualified_ds_tracks = []
        qualified_sf_tracks = []

        for trk in M.Reco_MuonTracks:
            fs = trk.getFitStatus()
            if not fs.isFitConverged() or fs.getNdf() == 0:
                continue
            chi2ndf = fs.getChi2() / fs.getNdf()
            if chi2ndf >= 5.0:
                continue

            fst = trk.getFittedState()
            mom = fst.getMom()
            if mom.z() == 0:
                continue
            slope_x = mom.x() / mom.z()
            slope_y = mom.y() / mom.z()
            if abs(slope_x) >= 0.1 or abs(slope_y) >= 0.1:
                continue

            ttype = trk.getTrackType() if hasattr(trk, "getTrackType") else trk.GetUniqueID()
            track_info = {
                "chi2ndf": chi2ndf,
                "track": trk,
                "pos": fst.getPos(),
                "mom": mom
            }
            if ttype == 3:
                qualified_ds_tracks.append(track_info)
            elif ttype == 1:
                qualified_sf_tracks.append(track_info)

        best_ds = min(qualified_ds_tracks, key=lambda x: x["chi2ndf"]) if qualified_ds_tracks else None
        best_sf = min(qualified_sf_tracks, key=lambda x: x["chi2ndf"]) if qualified_sf_tracks else None

        if not best_ds and not best_sf:
            continue

        analysis.current_ds_track = best_ds["track"] if best_ds else None

        # 2. Extract DS Reference Time
        tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
        has_valid_ds = False
        tds0_val = None
        if isinstance(tds0, (tuple, list)):
            if tds0[0] != -999.:
                tds0_val = tds0[0]
        elif tds0 != -999.:
            tds0_val = tds0

        if tds0_val is not None and (tds0_min <= tds0_val <= tds0_max):
            has_valid_ds = True

        # 3. Extract SciFi Reference Time
        tsf0 = analysis.GetScifiAverageTime(M.Scifi, event.Digi_ScifiHits, mode="tsf0")
        has_valid_sf = False
        tsf0_val = None
        if isinstance(tsf0, (tuple, list)):
            if tsf0[0] != -999.:
                tsf0_val = tsf0[0]
        elif tsf0 != -999.:
            tsf0_val = tsf0

        if tsf0_val is not None and (tsf0_min <= tsf0_val <= tsf0_max):
            has_valid_sf = True
        else:
            tsf0_val = None

        if not has_valid_ds and not has_valid_sf:
            continue

        # 4. Predict crossed bars
        expected_us_bars = {}
        if best_ds:
            pos_ds = best_ds["pos"]
            mom_ds = best_ds["mom"]
            for plane, zEx in us_z_planes.items():
                lam = (zEx - pos_ds.z()) / mom_ds.z()
                xEx = pos_ds.x() + lam * mom_ds.x()
                yEx = pos_ds.y() + lam * mom_ds.y()
                node = nav.FindNode(xEx, yEx, zEx)
                if not node or node.GetName() == "cave_1":
                    for dz in [0.4, -0.4, 0.8, -0.8]:
                        node = nav.FindNode(xEx, yEx, zEx + dz)
                        if node and node.GetName() != "cave_1":
                            break
                if node:
                    node_name = node.GetName()
                    if node_name.startswith("volMuUpstreamBar_"):
                        try:
                            bar_det_id = int(node_name.split("_")[-1])
                            if passes_fiducial(bar_det_id, xEx, yEx):
                                expected_us_bars[plane] = (bar_det_id, xEx)
                        except ValueError:
                            pass

        expected_veto_bars = {}
        if best_sf:
            pos_sf = best_sf["pos"]
            mom_sf = best_sf["mom"]
            for plane, zEx in veto_z_planes.items():
                lam = (zEx - pos_sf.z()) / mom_sf.z()
                xEx = pos_sf.x() + lam * mom_sf.x()
                yEx = pos_sf.y() + lam * mom_sf.y()
                node = nav.FindNode(xEx, yEx, zEx)
                if not node or node.GetName() == "cave_1":
                    for dz in [0.4, -0.4, 0.8, -0.8]:
                        node = nav.FindNode(xEx, yEx, zEx + dz)
                        if node and node.GetName() != "cave_1":
                            break
                if node:
                    node_name = node.GetName()
                    if node_name.startswith("volVetoBar_") or node_name.startswith("volVetoBar_ver_"):
                        try:
                            bar_det_id = int(node_name.split("_")[-1])
                            if passes_fiducial(bar_det_id, xEx, yEx):
                                pred_val = yEx if plane >= 2 else xEx
                                expected_veto_bars[plane] = (bar_det_id, pred_val)
                        except ValueError:
                            pass

        expected_ds_bars = {}
        if best_ds:
            pos_ds = best_ds["pos"]
            mom_ds = best_ds["mom"]
            for (st, orientation), zEx in ds_z_planes.items():
                lam = (zEx - pos_ds.z()) / mom_ds.z()
                xEx = pos_ds.x() + lam * mom_ds.x()
                yEx = pos_ds.y() + lam * mom_ds.y()
                node = nav.FindNode(xEx, yEx, zEx)
                if not node or node.GetName() == "cave_1":
                    for dz in [0.4, -0.4, 0.8, -0.8]:
                        node = nav.FindNode(xEx, yEx, zEx + dz)
                        if node and node.GetName() != "cave_1":
                            break
                if node:
                    node_name = node.GetName()
                    if orientation == "hor" and node_name.startswith("volMuDownstreamBar_hor_"):
                        try:
                            bar_det_id = int(node_name.split("_")[-1])
                            if passes_fiducial(bar_det_id, xEx, yEx):
                                expected_ds_bars[(st, "hor")] = (bar_det_id, xEx)
                        except ValueError:
                            pass
                    elif orientation == "ver" and node_name.startswith("volMuDownstreamBar_ver_"):
                        try:
                            bar_det_id = int(node_name.split("_")[-1])
                            if passes_fiducial(bar_det_id, xEx, yEx):
                                expected_ds_bars[(st, "ver")] = (bar_det_id, yEx)
                        except ValueError:
                            pass

        # 5. Loop over Digi_MuFilterHits and apply Time-Walk correction
        for hit in event.Digi_MuFilterHits:
            if not hit.isValid():
                continue
            detID = hit.GetDetectorID()
            s, p, b = analysis.parseDetID(detID)

            if s == 2:
                if not best_ds or p not in expected_us_bars or expected_us_bars[p][0] != detID:
                    continue
                pos_pred = expected_us_bars[p][1]
            elif s == 1:
                if not best_sf or p not in expected_veto_bars or expected_veto_bars[p][0] != detID:
                    continue
                pos_pred = expected_veto_bars[p][1]
            elif s == 3:
                orientation = "ver" if b >= 60 else "hor"
                key = (p, orientation)
                if not best_ds or key not in expected_ds_bars or expected_ds_bars[key][0] != detID:
                    continue
                pos_pred = expected_ds_bars[key][1]
            else:
                continue

            channels_t = hit.GetAllTimes()
            signals_dict = dict(hit.GetAllSignals())
            for item in channels_t:
                sipm_num, clock = item
                if sipm_num < 0 or sipm_num > 15:
                    continue

                if s == 2 and analysis.IsSmallSiPMchannel(sipm_num):
                    continue

                if s == 1 and p >= 2 and sipm_num >= 8:
                    continue

                if s == 3 and b < 60 and sipm_num > 1:
                    continue

                if s == 3 and b >= 60 and sipm_num > 0:
                    continue

                if f"{detID}_{sipm_num}" == "21005_15":
                    continue

                qdc = signals_dict.get(sipm_num, -999.)
                if qdc == -999. or qdc <= 0:
                    continue

                t_sipm = clock * tdc2ns
                ch_key = f"{detID}_{sipm_num}"

                if has_valid_ds:
                    shift_ds = get_tw_shift(tw_params, "DS", ch_key, qdc, tw_summary)
                    dt_ds = (tds0_val - t_sipm) - shift_ds
                    get_hist(ch_key, "dt-DS").Fill(pos_pred, dt_ds)

                if has_valid_sf:
                    shift_sf = get_tw_shift(tw_params, "SF", ch_key, qdc, tw_summary)
                    dt_sf = (tsf0_val - t_sipm) - shift_sf
                    get_hist(ch_key, "dt-SF").Fill(pos_pred, dt_sf)

    # 6. Write channel histograms into structured temp ROOT file
    out_f = ROOT.TFile.Open(temp_output, "RECREATE")
    for ch_key, hists in hist_cache.items():
        ch_dir = out_f.mkdir(ch_key)
        ch_dir.cd()
        if "dt-DS" in hists:
            hists["dt-DS"].Write("dt-DS")
        if "dt-SF" in hists:
            hists["dt-SF"].Write("dt-SF")
    out_f.Close()

    print(f" ~ Run {run_nr} ({category}) complete: filled {len(hist_cache)} Time-Walk corrected SiPM channels.", flush=True)
    os._exit(0)


def main():
    args = parse_args()

    # Worker dispatch
    if args.worker:
        run_worker(
            run_nr=int(args.run_number),
            break_events=args.break_events,
            temp_output=args.temp_output or args.output_file,
            partition=args.partition,
            geo_file_override=args.geo_file,
            windows_json=args.windows_json,
            timewalk_dir=args.timewalk_dir,
            timewalk_file=args.timewalk_file,
            require_veto_scifi1=args.require_veto_scifi1
        )
        return

    # Master pipeline mode
    csv_path = args.csv_path
    if not os.path.exists(csv_path):
        for candidate in [
            "/afs/cern.ch/work/i/idioniso/snd-veto-us/runs_2022.csv",
            os.path.join(_REPO_ROOT, "runs_2022.csv"),
            "runs_2022.csv"
        ]:
            if os.path.exists(candidate):
                csv_path = candidate
                break

    if not os.path.exists(csv_path):
        print(f"[ERROR] Could not find runs catalog at: {csv_path}", file=sys.stderr)
        sys.exit(1)

    import pandas as pd
    df = pd.read_csv(csv_path)

    if args.run_number:
        run_list = [int(x.strip()) for x in str(args.run_number).split(",") if x.strip()]
        runs_to_process = [(r, get_run_category(r)) for r in run_list]
    else:
        mask = (
            (df["entries"] > 3000000) &
            (df["luminosity_pb"] > 0) &
            (df["is_physics_collision"] == True)
        )
        filtered_df = df[mask].sort_values("run_number")
        runs_to_process = [(int(row["run_number"]), get_run_category(int(row["run_number"]))) for _, row in filtered_df.iterrows()]
        print(f"Loaded {len(runs_to_process)} qualifying runs from {csv_path} (>3M entries, lumi > 0, is_physics_collision==True).")

    out_root_path = args.output_file
    out_dir = os.path.dirname(os.path.abspath(out_root_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print("======================================================================")
    print(" SND@LHC Time-Walk Corrected c_scint Extraction Pipeline")
    print(f" Target ROOT File   : {out_root_path}")
    print(f" Time-Walk Fits Dir : {args.timewalk_dir}")
    print(f" Break Event Limit  : {args.break_events:,} events/run (0 = full run)")
    print(f" Number of Runs     : {len(runs_to_process)}")
    print(f" Parallel Workers   : {args.n_workers} processes")
    print("======================================================================")

    import ROOT
    ROOT.gROOT.SetBatch(True)
    file_lock = threading.Lock()

    def process_run(run_item):
        r_num, r_cat = run_item
        with tempfile.NamedTemporaryFile(suffix=".root", delete=False) as tf:
            tmp_root = tf.name

        cmd = [
            sys.executable,
            "-X", "faulthandler",
            os.path.abspath(__file__),
            "--worker",
            "-r", str(r_num),
            "-b", str(args.break_events),
            "--windows-json", os.path.abspath(args.windows_json),
            "--timewalk-dir", os.path.abspath(args.timewalk_dir),
            "-o", tmp_root
        ]
        if args.timewalk_file:
            cmd.extend(["--timewalk-file", os.path.abspath(args.timewalk_file)])
        if args.geo_file:
            cmd.extend(["-g", os.path.abspath(args.geo_file)])
        if not args.require_veto_scifi1:
            cmd.append("--no-veto-scifi1")

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if res.returncode != 0:
            print(f"[ERROR] Run {r_num} failed:\n{res.stdout}", file=sys.stderr)
            if os.path.exists(tmp_root):
                os.remove(tmp_root)
            return

        with file_lock:
            master_f = ROOT.TFile.Open(out_root_path, "UPDATE")
            cat_dir = master_f.GetDirectory(r_cat) or master_f.mkdir(r_cat)
            run_dir = cat_dir.GetDirectory(f"run{r_num}") or cat_dir.mkdir(f"run{r_num}")

            part_f = ROOT.TFile.Open(tmp_root, "READ")
            for key in part_f.GetListOfKeys():
                ch_name = key.GetName()
                ch_dir = run_dir.GetDirectory(ch_name) or run_dir.mkdir(ch_name)
                src_ch_dir = part_f.Get(ch_name)
                for h_key in src_ch_dir.GetListOfKeys():
                    h_name = h_key.GetName()
                    src_h = src_ch_dir.Get(h_name)
                    dest_h = ch_dir.Get(h_name)
                    if dest_h:
                        dest_h.Add(src_h)
                        ch_dir.cd()
                        dest_h.Write(h_name, ROOT.TObject.kOverwrite)
                    else:
                        ch_dir.cd()
                        src_h.Write(h_name)
            part_f.Close()
            master_f.Close()

        if os.path.exists(tmp_root):
            os.remove(tmp_root)
        print(f" -> Merged Run {r_num} ({r_cat}) into {out_root_path}")

    with ThreadPoolExecutor(max_workers=args.n_workers) as executor:
        futures = {executor.submit(process_run, item): item for item in runs_to_process}
        for future in as_completed(futures):
            future.result()

    print("[SUCCESS] All runs completed.")


if __name__ == "__main__":
    main()
