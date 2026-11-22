#!/usr/bin/env python3
"""
timewalk.py
-----------
Extracts the Time-Walk 2D distributions (dt vs QDC) for each SiPM channel
in the Veto and Upstream systems after Time-of-Flight (propagation speed) correction:
  dt^DS = t0^DS - t_SiPM^ToF
  dt^SF = t0^SF - t_SiPM^ToF

Propagation / ToF Correction logic (following TimeWalk.py & AnalysisFunctions.py):
  MuFilter.GetPosition(detID, A, B)
  xref = 0.5 * (A.x() + B.x())
  dx = x_pred - xref
  t_raw = clock * TDC2ns
  dt_prop = dx / c_scint
  If SiPM < 8:  t_ToF = t_raw + dt_prop
  Else (>= 8):  t_ToF = t_raw - dt_prop
  dt = t0 - t_ToF

Selection logic (matching mufilter_cscint.py):
  - Upstream bars (system 2, detID 20000..24009):
      Tracked by qualified DS track (reconstructed DS track,
      chi2ndf < 5, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad).
  - Veto bars (system 1, detID 10000..11006):
      Tracked by qualified SciFi track (reconstructed SciFi track,
      chi2ndf < 5, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad).

Light speed constants:
  Loaded per-channel from precalculated fit JSON files:
    /eos/user/i/idioniso/Timing/cscint/fits/run<RUN>_cscint.json
  If a channel fit is missing or invalid, falls back to the run-averaged
  weighted mean from the summary block, then to median/placeholder.

Output ROOT File Structure:
  <catI | catII | catIII>/runXXXX/<detID_SiPM>/
    ├── dtvqdc-DS            (dt^DS vs QDC using channel-specific c_scint)
    ├── dtvqdc-SF            (dt^SF vs QDC using channel-specific c_scint)
    ├── dtvqdc-DS-unified    [optional --include-unified]
    └── dtvqdc-SF-unified    [optional --include-unified]
"""

import os
import sys
import glob
import json
import tempfile
import argparse
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_DEFAULT_WINDOWS_JSON = os.path.join(_REPO_ROOT, "config", "ref_time_windows.json")
_DEFAULT_CSCINT_DIR = "/eos/user/i/idioniso/Timing/cscint/fits"
_DEFAULT_OUTPUT = "/eos/user/i/idioniso/Timing/timewalk_2022.root"
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


def load_run_cscint(run_nr: int, cscint_file: str = None, cscint_dir: str = _DEFAULT_CSCINT_DIR, placeholder: float = 13.5):
    """
    Loads channel-specific and run-unified c_scint constants from JSON.
    Returns:
      specific_cscint: {'DS': {ch: val}, 'SF': {ch: val}}
      unified_cscint:  {'DS': val, 'SF': val}
    """
    candidates = []
    if cscint_file and os.path.exists(cscint_file):
        candidates.append(cscint_file)

    if cscint_dir:
        candidates.extend([
            os.path.join(cscint_dir, f"run{run_nr}_cscint.json"),
            os.path.join(cscint_dir, f"run{run_nr:06d}_cscint.json"),
            os.path.join(cscint_dir, f"run_{run_nr}_cscint.json"),
            os.path.join(cscint_dir, f"run{run_nr}.json"),
        ])

    candidates.extend([
        f"/eos/user/i/idioniso/Timing/cscint/fits/run{run_nr}_cscint.json",
        f"/eos/user/i/idioniso/Timing/cscint/runs/fits/run{run_nr}_cscint.json",
        f"/eos/user/i/idioniso/Timing/run{run_nr}/run{run_nr}_timing_calibration.json",
    ])

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

    specific = {"DS": {}, "SF": {}}
    unified = {"DS": placeholder, "SF": placeholder}

    if not data:
        print(f"[INFO] [Run {run_nr}] No precomputed c_scint file found. Using placeholder: {placeholder:.2f} cm/ns", flush=True)
        return specific, unified

    for ref in ("DS", "SF"):
        if ref in data and isinstance(data[ref], dict):
            for k, v in data[ref].items():
                if isinstance(v, dict) and "c_scint" in v:
                    val = float(v["c_scint"])
                elif isinstance(v, (list, tuple)) and len(v) >= 1:
                    val = float(v[0])
                else:
                    try:
                        val = float(v)
                    except (ValueError, TypeError):
                        continue
                if 5.0 < val < 30.0:
                    specific[ref][k] = val

        # Fallback to general 'cscint' dictionary if reference key absent
        elif "cscint" in data and isinstance(data["cscint"], dict):
            for k, v in data["cscint"].items():
                val = float(v[0]) if isinstance(v, (list, tuple)) else float(v)
                if 5.0 < val < 30.0:
                    specific[ref][k] = val

        # Determine unified speed
        if "summary" in data and ref in data["summary"] and "weighted_mean" in data["summary"][ref]:
            w_mean = float(data["summary"][ref]["weighted_mean"])
            if 5.0 < w_mean < 30.0:
                unified[ref] = w_mean
            else:
                vals = list(specific[ref].values())
                unified[ref] = float(np.median(vals)) if vals else placeholder
        else:
            vals = list(specific[ref].values())
            unified[ref] = float(np.median(vals)) if vals else placeholder

    # If SF constants are empty, fall back to DS constants (matching TimeWalk.py logic)
    if not specific["SF"] and specific["DS"]:
        print(f"[INFO] [Run {run_nr}] c_scint constants for SF empty; falling back to DS bar speeds ({len(specific['DS'])} channels).", flush=True)
        specific["SF"] = dict(specific["DS"])
        unified["SF"] = unified["DS"]

    print(f"[INFO] [Run {run_nr}] Loaded c_scint constants from {loaded_path}: DS={len(specific['DS'])} (unified={unified['DS']:.2f} cm/ns), SF={len(specific['SF'])} (unified={unified['SF']:.2f} cm/ns)", flush=True)
    return specific, unified


def run_worker(
    run_nr,
    break_events,
    temp_output,
    partition=-1,
    geo_file_override=None,
    windows_json=None,
    cscint_dir=_DEFAULT_CSCINT_DIR,
    cscint_file=None,
    include_unified=False,
    require_veto_scifi1=True
):
    """Processes a single run (or partition) in an isolated subprocess to produce timewalk histograms."""
    import ROOT
    ROOT.gROOT.SetBatch(True)
    ROOT.PyConfig.IgnoreCommandLineOptions = True
    ROOT.gErrorIgnoreLevel = ROOT.kError

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
    elif os.path.exists(geo_file):
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

    # Pre-fetch geometry references and timing settings
    nav = ROOT.gGeoManager.GetCurrentNavigator()
    mu_filter = M.MuFilter
    tdc2ns = analysis.TDC2ns
    tds0_min, tds0_max = get_tds0_window(run_nr, windows_json)
    tsf0_min, tsf0_max = get_tsf0_window(run_nr, windows_json)
    category = get_run_category(run_nr)

    # Load c_scint constants
    specific_cscint, unified_cscint = load_run_cscint(
        run_nr=run_nr,
        cscint_file=cscint_file,
        cscint_dir=cscint_dir
    )

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
                W = pt.getRawMeasurement()
                detID = W.getDetId()
                s, p, b = self.parseDetID(detID)
                if s != 3 or detID not in stations:
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

    # Cache bar central positions
    bar_pos_cache = {}
    a_tmp = ROOT.TVector3()
    b_tmp = ROOT.TVector3()

    def get_bar_pos_ref(det_id, is_vertical=False):
        key = (det_id, is_vertical)
        if key not in bar_pos_cache:
            mu_filter.GetPosition(det_id, a_tmp, b_tmp)
            if is_vertical:
                bar_pos_cache[key] = 0.5 * (a_tmp.y() + b_tmp.y())
            else:
                bar_pos_cache[key] = 0.5 * (a_tmp.x() + b_tmp.x())
        return bar_pos_cache[key]

    # Pre-calculate z planes for all systems
    us_z_planes = {}
    n_us_planes = M.systemAndPlanes.get(2, 5)
    for pl in range(n_us_planes):
        mu_filter.GetPosition(20000 + pl * 1000, a_tmp, b_tmp)
        us_z_planes[pl] = (a_tmp.z() + b_tmp.z()) / 2.0

    veto_z_planes = {}
    n_veto_planes = M.systemAndPlanes.get(1, 2)
    for pl in range(n_veto_planes):
        mu_filter.GetPosition(10000 + pl * 1000, a_tmp, b_tmp)
        veto_z_planes[pl] = (a_tmp.z() + b_tmp.z()) / 2.0

    ds_z_planes = {}
    for st in range(4):
        if st < 3:
            mu_filter.GetPosition(30000 + st * 1000, a_tmp, b_tmp)
            ds_z_planes[(st, "hor")] = (a_tmp.z() + b_tmp.z()) / 2.0
        mu_filter.GetPosition(30000 + st * 1000 + 60, a_tmp, b_tmp)
        ds_z_planes[(st, "ver")] = (a_tmp.z() + b_tmp.z()) / 2.0

    # Histogram cache: channel_key -> {hist_type: TH2F}
    hist_cache = {}

    def get_hist(channel_key, hist_type):
        if channel_key not in hist_cache:
            hist_cache[channel_key] = {}
        if hist_type not in hist_cache[channel_key]:
            # QDC: 200 bins [0, 200]
            nbins_qdc, qdc_min, qdc_max = 200, 0.0, 200.0

            if "SF" in hist_type:
                # SciFi ref time difference: 500 bins [-45, 5] ns (0.1 ns/bin)
                nbins_dt, dt_min, dt_max = 500, -45.0, 5.0
                ref_label = "SciFi Ref"
                y_title = "t_{0}^{SF} - t_{SiPM}^{ToF} [ns]"
            else:
                # DS ref time difference: 400 bins [-10, 30] ns (0.1 ns/bin)
                nbins_dt, dt_min, dt_max = 400, -10.0, 30.0
                ref_label = "DS Ref"
                y_title = "t_{0}^{DS} - t_{SiPM}^{ToF} [ns]"

            sub_label = "Unified c_{scint}" if "unified" in hist_type else "Specific c_{scint}"
            title = f"{channel_key} Time-Walk ({sub_label}, {ref_label}, Run {run_nr});QDC_{{SiPM}} [a.u.];{y_title}"
            h_name = f"{hist_type}_{channel_key}"

            h = ROOT.TH2F(h_name, title, nbins_qdc, qdc_min, qdc_max, nbins_dt, dt_min, dt_max)
            h.SetDirectory(0)
            hist_cache[channel_key][hist_type] = h
        return hist_cache[channel_key][hist_type]

    def passes_fiducial(det_id, x_ex, y_ex, cut=5.0):
        a_pt, b_pt = ROOT.TVector3(), ROOT.TVector3()
        mu_filter.GetPosition(det_id, a_pt, b_pt)
        subsys, pl, bar = analysis.parseDetID(det_id)
        if (subsys == 1 and pl == 2) or (subsys == 3 and bar >= 60):
            return (min(a_pt.y(), b_pt.y()) + cut) <= y_ex <= (max(a_pt.y(), b_pt.y()) - cut)
        else:
            return (min(a_pt.x(), b_pt.x()) + cut) <= x_ex <= (max(a_pt.x(), b_pt.x()) - cut)

    events_to_process = M.GetEntries()
    if max_ev > 0:
        events_to_process = min(events_to_process, max_ev)

    heartbeat = max(1000, events_to_process // 10)
    print(f" ~ [Run {run_nr}] Processing {events_to_process:,} events (Category {category})...", flush=True)

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

        # 1. Select qualified tracks:
        #    - DS tracks (track_type == 3) for Upstream bars (s == 2)
        #    - SciFi tracks (track_type == 1) for Veto bars (s == 1)
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

        # 2. Extract DS Reference Time and apply window cut
        has_valid_ds = False
        tds0_val = None
        if best_ds:
            tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
            if isinstance(tds0, (tuple, list)):
                if tds0[0] != -999.:
                    tds0_val = tds0[0]
            elif tds0 != -999.:
                tds0_val = tds0

            if tds0_val is not None and (tds0_min <= tds0_val <= tds0_max):
                has_valid_ds = True

        # 3. Extract SciFi Reference Time and apply window cut
        has_valid_sf = False
        tsf0_val = None
        if best_sf:
            tsf0 = analysis.GetScifiAverageTime(M.Scifi, event.Digi_ScifiHits, mode="tsf0")
            if isinstance(tsf0, (tuple, list)):
                if tsf0[0] != -999.:
                    tsf0_val = tsf0[0]
            elif tsf0 != -999.:
                tsf0_val = tsf0

            if tsf0_val is not None and (tsf0_min <= tsf0_val <= tsf0_max):
                has_valid_sf = True

        if not has_valid_ds and not has_valid_sf:
            continue

        # 4. Predict crossed bars:
        #    - Upstream planes crossed by DS track
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

        #    - Veto planes crossed by SciFi track
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

        #    - Downstream planes crossed by DS track
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

        # 5. Loop over Digi_MuFilterHits for Veto (s == 1), Upstream (s == 2), and Downstream (s == 3)
        for hit in event.Digi_MuFilterHits:
            if not hit.isValid():
                continue
            detID = hit.GetDetectorID()
            s, p, b = analysis.parseDetID(detID)

            # Upstream bars (s == 2): ALWAYS use DS track
            if s == 2:
                if not best_ds or p not in expected_us_bars or expected_us_bars[p][0] != detID:
                    continue
                pos_pred = expected_us_bars[p][1]

            # Veto bars (s == 1): ALWAYS use SciFi track
            elif s == 1:
                if not best_sf or p not in expected_veto_bars or expected_veto_bars[p][0] != detID:
                    continue
                pos_pred = expected_veto_bars[p][1]

            # Downstream bars (s == 3): ALWAYS use DS track
            elif s == 3:
                orientation = "ver" if b >= 60 else "hor"
                key = (p, orientation)
                if not best_ds or key not in expected_ds_bars or expected_ds_bars[key][0] != detID:
                    continue
                pos_pred = expected_ds_bars[key][1]

            else:
                continue

            is_vertical = (s == 1 and p >= 2) or (s == 3 and b >= 60)
            ref_pos = get_bar_pos_ref(detID, is_vertical=is_vertical)
            dx = pos_pred - ref_pos

            channels_t = hit.GetAllTimes()
            signals_dict = dict(hit.GetAllSignals())
            for item in channels_t:
                sipm_num, clock = item
                if sipm_num < 0 or sipm_num > 15:
                    continue

                # Drop small SiPMs in US
                if s == 2 and analysis.IsSmallSiPMchannel(sipm_num):
                    continue

                # For vertical veto bars (subsystem 1, plane 2), readout is top side only (0..7)
                if s == 1 and p >= 2 and sipm_num >= 8:
                    continue

                # For Downstream horizontal bars (s == 3, b < 60), readout is 2 channels: 0 (Left), 1 (Right)
                if s == 3 and b < 60 and sipm_num > 1:
                    continue

                # For Downstream vertical bars (s == 3, b >= 60), readout is top side only: channel 0
                if s == 3 and b >= 60 and sipm_num > 0:
                    continue

                # Skip known dead channel
                ch_key = f"{detID}_{sipm_num}"
                if ch_key == "21005_15":
                    continue

                # Require valid positive QDC signal above threshold
                qdc = signals_dict.get(sipm_num, -999.)
                if qdc == -999. or qdc <= 0:
                    continue

                t_raw = clock * tdc2ns

                # Side sign convention
                if is_vertical:
                    sign = 1.0
                elif s == 3:
                    sign = 1.0 if sipm_num == 0 else -1.0
                else:
                    sign = 1.0 if sipm_num < 8 else -1.0

                # A. DS Reference TimeWalk
                if has_valid_ds:
                    c_ds = specific_cscint["DS"].get(ch_key, unified_cscint["DS"])
                    if c_ds and c_ds > 0:
                        t_tof = t_raw + sign * (dx / c_ds)
                        dt_ds = tds0_val - t_tof
                        get_hist(ch_key, "dtvqdc-DS").Fill(qdc, dt_ds)

                    if include_unified and unified_cscint["DS"] and unified_cscint["DS"] > 0:
                        t_tof_uni = t_raw + sign * (dx / unified_cscint["DS"])
                        dt_ds_uni = tds0_val - t_tof_uni
                        get_hist(ch_key, "dtvqdc-DS-unified").Fill(qdc, dt_ds_uni)

                # B. SciFi Reference TimeWalk
                if has_valid_sf:
                    c_sf = specific_cscint["SF"].get(ch_key, unified_cscint["SF"])
                    if c_sf and c_sf > 0:
                        t_tof = t_raw + sign * (dx / c_sf)
                        dt_sf = tsf0_val - t_tof
                        get_hist(ch_key, "dtvqdc-SF").Fill(qdc, dt_sf)

                    if include_unified and unified_cscint["SF"] and unified_cscint["SF"] > 0:
                        t_tof_uni = t_raw + sign * (dx / unified_cscint["SF"])
                        dt_sf_uni = tsf0_val - t_tof_uni
                        get_hist(ch_key, "dtvqdc-SF-unified").Fill(qdc, dt_sf_uni)

    # 6. Write channel histograms into structured temp ROOT file
    out_f = ROOT.TFile.Open(temp_output, "RECREATE")
    for ch_key, hists in hist_cache.items():
        ch_dir = out_f.mkdir(ch_key)
        ch_dir.cd()
        for h_type, h in hists.items():
            h.Write(h_type, ROOT.TObject.kOverwrite)
    out_f.Close()
    print(f" ~ [Run {run_nr}] Temp output written with {len(hist_cache)} channels.", flush=True)
    os._exit(0)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract ToF-corrected Time-Walk distributions (dt vs QDC) for each SiPM channel."
    )
    parser.add_argument(
        "-r", "--run", "--run-number",
        dest="run_number",
        type=str,
        default=None,
        help="Run number or comma-separated list of runs to process (default: all qualifying 2022 runs)"
    )
    parser.add_argument(
        "-c", "--category",
        dest="category",
        type=str,
        default=None,
        choices=["catI", "catII", "catIII"],
        help="Filter runs by time-alignment category (catI, catII, catIII)"
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
        default=_DEFAULT_OUTPUT,
        help="Single output ROOT file storing cat/run/detectorID_SiPM directories"
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        type=str,
        default="/afs/cern.ch/work/i/idioniso/snd-veto-us/runs_2022.csv",
        help="Path to runs_2022.csv catalog"
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
        "--cscint-dir",
        dest="cscint_dir",
        type=str,
        default=_DEFAULT_CSCINT_DIR,
        help="Path to directory containing run<RUN>_cscint.json fits (default: /eos/user/i/idioniso/Timing/cscint/fits)"
    )
    parser.add_argument(
        "--cscint-file",
        dest="cscint_file",
        type=str,
        default=None,
        help="Direct path to single c_scint JSON file"
    )
    parser.add_argument(
        "--include-unified",
        dest="include_unified",
        action="store_true",
        default=False,
        help="Also store unified c_scint histograms (dtvqdc-DS-unified, dtvqdc-SF-unified)"
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
            cscint_dir=args.cscint_dir,
            cscint_file=args.cscint_file,
            include_unified=args.include_unified,
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

    if args.category:
        runs_to_process = [item for item in runs_to_process if item[1] == args.category]
        print(f"Filtered to {len(runs_to_process)} runs matching category '{args.category}'.")

    out_root_path = args.output_file
    out_dir = os.path.dirname(os.path.abspath(out_root_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print("======================================================================")
    print(" SND@LHC ToF-Corrected Time-Walk Histogram Extraction Pipeline")
    print(f" Target ROOT File  : {out_root_path}")
    print(f" Break Event Limit : {args.break_events:,} events/run (0 = full run)")
    print(f" Number of Runs    : {len(runs_to_process)}")
    print(f" Parallel Workers  : {args.n_workers} processes")
    print(f" c_scint Directory : {args.cscint_dir}")
    print(f" Include Unified   : {args.include_unified}")
    print(" Reference Cut     : Category-dependent t0^DS & t0^SF windows applied")
    print("======================================================================")

    import ROOT
    ROOT.gROOT.SetBatch(True)
    file_lock = threading.Lock()

    def process_run(run_item):
        idx, (r, cat) = run_item
        run_dir_name = f"run{r}"

        # Resume check
        if not args.force and os.path.exists(out_root_path):
            with file_lock:
                chk_f = ROOT.TFile.Open(out_root_path, "READ")
                if chk_f and not chk_f.IsZombie():
                    cat_dir = chk_f.Get(cat)
                    if cat_dir:
                        r_dir = cat_dir.Get(run_dir_name)
                        if r_dir:
                            chk_f.Close()
                            print(f"[{idx}/{len(runs_to_process)}] Skipping {cat}/{run_dir_name} (already present).", flush=True)
                            return True
                    chk_f.Close()

        print(f"[{idx}/{len(runs_to_process)}] [START] Processing Run {r} ({cat})...", flush=True)

        with tempfile.NamedTemporaryFile(suffix=".root", delete=False) as tmp:
            temp_output = tmp.name

        try:
            worker_cmd = [
                sys.executable,
                "-X", "faulthandler",
                os.path.abspath(__file__),
                "--worker",
                "-r", str(r),
                "--break", str(args.break_events),
                "--temp-output", temp_output,
                "--partition", str(args.partition)
            ]
            if args.windows_json and os.path.exists(args.windows_json):
                worker_cmd.extend(["--windows-json", os.path.abspath(args.windows_json)])
            if args.cscint_dir:
                worker_cmd.extend(["--cscint-dir", os.path.abspath(args.cscint_dir)])
            if args.cscint_file:
                worker_cmd.extend(["--cscint-file", os.path.abspath(args.cscint_file)])
            if args.include_unified:
                worker_cmd.append("--include-unified")
            if args.geo_file:
                worker_cmd.extend(["-g", args.geo_file])
            if not args.require_veto_scifi1:
                worker_cmd.append("--no-veto-scifi1")

            worker_env = dict(os.environ, PYTHONUNBUFFERED="1")
            res = subprocess.run(worker_cmd, env=worker_env, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"[ERROR] Worker for Run {r} failed with exit code {res.returncode}:\n{res.stderr}", file=sys.stderr, flush=True)
                return False

            if not os.path.exists(temp_output) or os.path.getsize(temp_output) < 500:
                print(f"[ERROR] Worker for Run {r} produced missing or empty output file.", file=sys.stderr, flush=True)
                return False

            f_temp = ROOT.TFile.Open(temp_output, "READ")
            if not f_temp or f_temp.IsZombie():
                print(f"[ERROR] Could not open temp ROOT file for Run {r}.", file=sys.stderr, flush=True)
                return False

            # Read all channel subdirectories and clone histograms
            channels_data = {}
            for k in f_temp.GetListOfKeys():
                ch_name = k.GetName()
                ch_dir = f_temp.Get(ch_name)
                if not ch_dir or not ch_dir.IsA().InheritsFrom("TDirectory"):
                    continue
                channels_data[ch_name] = {}
                for h_type in ("dtvqdc-DS", "dtvqdc-SF", "dtvqdc-DS-unified", "dtvqdc-SF-unified"):
                    h = ch_dir.Get(h_type)
                    if h:
                        h.SetDirectory(0)
                        channels_data[ch_name][h_type] = h

            f_temp.Close()

            # Thread-safe write into master ROOT file
            with file_lock:
                f_master = ROOT.TFile.Open(out_root_path, "UPDATE")
                cat_dir = f_master.GetDirectory(cat)
                if not cat_dir:
                    cat_dir = f_master.mkdir(cat)
                cat_dir.cd()

                r_dir = cat_dir.GetDirectory(run_dir_name)
                if not r_dir:
                    r_dir = cat_dir.mkdir(run_dir_name)

                for ch_name, h_dict in channels_data.items():
                    r_dir.cd()
                    ch_dir = r_dir.GetDirectory(ch_name)
                    if not ch_dir:
                        ch_dir = r_dir.mkdir(ch_name)
                    ch_dir.cd()
                    for h_type, h_obj in h_dict.items():
                        h_obj.Write(h_type, ROOT.TObject.kOverwrite)

                f_master.Close()

            print(f"[{idx}/{len(runs_to_process)}] [SUCCESS] Saved {cat}/{run_dir_name} ({len(channels_data)} channels) into {out_root_path}")
            return True

        finally:
            if os.path.exists(temp_output):
                os.remove(temp_output)

    with ThreadPoolExecutor(max_workers=args.n_workers) as executor:
        futures = {executor.submit(process_run, item): item[1][0] for item in enumerate(runs_to_process, 1)}
        for future in as_completed(futures):
            r_num = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"[FATAL] Unhandled exception processing Run {r_num}: {e}", file=sys.stderr)

    print("\n======================================================================")
    print(f"[FINISHED] All requested runs processed. Output saved to: {out_root_path}")
    print("======================================================================")


if __name__ == "__main__":
    main()
