#!/usr/bin/env python3
"""
scifi_cscint.py
-------------------------
Analogous to mufilter_cscint.py, but for SciFi fiber clusters.
Extracts the difference between SiPM readout time and reference times:
  t_SiPM - t0^SF  and  t_SiPM - t0^DS
as a function of the predicted crossing coordinate (x_pred for horizontal planes,
y_pred for vertical planes) to extract the effective speed of light in SciFi fibers.

Detector & Mapping Logic:
  - 5 SciFi stations (stations 1..5).
  - Each station has:
      * Horizontal plane (T=0): fibers run along x, SiPM arrays on bottom/left (x ~ -46.5 cm).
        Measurement coordinate is y. Predicted light position is x_pred.
      * Vertical plane (T=1): fibers run along y, SiPM arrays on top (y ~ +54 cm).
        Measurement coordinate is x. Predicted light position is y_pred.
  - Clusters:
      Formed by all SiPM channels in that plane with |residual| <= 1 mm (0.1 cm)
      relative to the extrapolated SciFi track.
  - t_SiPM:
      Leading-edge arrival time of scintillation photons, defined as the earliest
      hit time in the cluster:
        t_SiPM = min_{i in cluster} (hit_i.GetTime() * TDC2ns)

Selection Cuts:
  - Pre-selection (BEFORE track reconstruction):
      1 <= nVetoHits <= 3  and  6 <= nScifiHits < 27
  - SciFi Track Quality:
      Reconstructed SciFi track (track_type == 1)
      chi2ndf < 5.0, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad
  - Reference times:
      t0^SF and t0^DS must fall within the qualifying run windows.

Output ROOT Structure:
  <catI | catII | catIII>/runXXXX/SF<S><H|V>_<M>_<R>/
    ├── dt-SF
    ├── dt-DS
    ├── cluster_size
    └── residual_meas
    ├── cluster_size
    └── residual_meas
"""

import os
import sys
import json
import time
import argparse
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

_DEFAULT_WINDOWS_JSON = os.path.join(_REPO_ROOT, "config", "ref_time_windows.json")
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
    windows = get_ref_windows_cache(json_path)
    win = windows.get(str(run_nr))
    if win and win.get("ds_t_min") is not None and win.get("ds_t_max") is not None:
        return float(win["ds_t_min"]), float(win["ds_t_max"])
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
    if run_nr is not None:
        windows = get_ref_windows_cache(json_path)
        win = windows.get(str(run_nr))
        if win and win.get("sf_t_min") is not None and win.get("sf_t_max") is not None:
            return float(win["sf_t_min"]), float(win["sf_t_max"])
    return -0.5, 6.0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract t_SiPM - t0^SF and t_SiPM - t0^DS distributions vs predicted position for SciFi clusters."
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
        help="Break processing if processed events exceed this number (default: 0 = full partition)"
    )
    parser.add_argument(
        "-j", "--threads", "--jobs", "--workers",
        dest="n_workers",
        type=int,
        default=4,
        help="Number of parallel worker processes (default: 4)"
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        type=str,
        default="/tmp/scifi_cscint.root",
        help="Output ROOT file path (default: /tmp/scifi_cscint.root)"
    )
    parser.add_argument(
        "-P", "--partition",
        dest="partition",
        type=int,
        default=-1,
        help="Data partition number (-1 for all partitions, default: -1)"
    )
    parser.add_argument(
        "-g", "--geofile",
        dest="geo_file",
        type=str,
        default=None,
        help="Optional override for geometry file"
    )
    parser.add_argument(
        "--windows-json",
        dest="windows_json",
        type=str,
        default=_DEFAULT_WINDOWS_JSON,
        help="Path to precalculated reference windows JSON"
    )
    parser.add_argument(
        "--worker",
        dest="worker",
        action="store_true",
        default=False,
        help="Run single worker process directly without fork"
    )
    parser.add_argument(
        "--temp-output",
        dest="temp_output",
        type=str,
        default=None,
        help="Direct path to write output ROOT file in worker mode"
    )
    return parser.parse_args()


def run_worker(run_nr, break_events, temp_output, partition=-1, geo_file_override=None, windows_json=None):
    """Processes a single run partition in an isolated subprocess."""
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

    data_path = DataManager.get_data_base_path(run_nr)
    if not data_path:
        raise RuntimeError(f"Could not resolve data base path for run {run_nr}")

    geo_file = geo_file_override or DataManager.get_geo_path_for_run(run_nr)
    if not geo_file:
        raise RuntimeError(f"Could not resolve geometry file for run {run_nr}")

    server = os.environ.get("EOSSHIP", "root://eospublic.cern.ch/")
    if not server.endswith("/"):
        server += "/"

    if data_path.startswith(server):
        data_path = data_path[len(server):]
    elif data_path.startswith("root://eospublic.cern.ch/"):
        data_path = data_path[len("root://eospublic.cern.ch/"):]
    if not data_path.endswith("/"):
        data_path += "/"

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

    # Pre-selection optimization: hook track_task.ExecuteTask to ONLY run on preselected events
    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")

    orig_ExecTask = track_task.ExecuteTask

    def filtered_ExecuteTask(option="ScifiDS"):
        event = M.eventTree
        nVeto = sum(1 for h in event.Digi_MuFilterHits if h.isValid() and (h.GetDetectorID() // 10000 == 1))
        nScifi = sum(1 for h in event.Digi_ScifiHits if h.isValid())
        if not (1 <= nVeto <= 3 and 6 <= nScifi < 27):
            return
        orig_ExecTask(option)

    track_task.ExecuteTask = filtered_ExecuteTask

    FairTasks = [track_task]
    M = Monitor.Monitoring(options, FairTasks)
    M.M = M
    analysis = af.Analysis(options)
    analysis.SetTask(M)
    scifi = M.Scifi
    tdc2ns = analysis.TDC2ns

    tds0_min, tds0_max = get_tds0_window(run_nr, windows_json)
    tsf0_min, tsf0_max = get_tsf0_window(run_nr, windows_json)
    category = get_run_category(run_nr)

    # Monkey-patch GetDSHaverage for safe DS reference time calculation
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

    # Calculate plane z positions
    plane_z = {}
    A_tmp, B_tmp = ROOT.TVector3(), ROOT.TVector3()
    for s in range(1, 6):
        scifi.GetSiPMPosition(s * 1000000, A_tmp, B_tmp)
        plane_z[(s, 0)] = (A_tmp.z() + B_tmp.z()) / 2.0
        scifi.GetSiPMPosition(s * 1000000 + 100000, A_tmp, B_tmp)
        plane_z[(s, 1)] = (A_tmp.z() + B_tmp.z()) / 2.0

    z_station1 = plane_z.get((1, 0), 300.0)

    # Histogram cache: sipm_key -> {'dt-SF': TH2F, 'dt-DS': TH2F, ...}
    hist_cache = {}

    def get_hist(sipm_key, hist_type):
        if sipm_key not in hist_cache:
            hist_cache[sipm_key] = {}
        if hist_type not in hist_cache[sipm_key]:
            is_vert = "V" in sipm_key.split("_")[0]
            if is_vert:
                # Vertical plane: measurement is x, light propagates along y (10 <= y <= 58 cm)
                pos_name = "y"
                nbins_pos, pos_min, pos_max = 48, 10.0, 58.0
            else:
                # Horizontal plane: measurement is y, light propagates along x (-50 <= x <= -5 cm)
                pos_name = "x"
                nbins_pos, pos_min, pos_max = 45, -50.0, -5.0

            if hist_type == "dt-SF":
                title = f"{sipm_key} t_{{SiPM}} - t_{{0}}^{{SF}} vs {pos_name} (Run {run_nr});{pos_name}_{{predicted}} [cm];t_{{SiPM}} - t_{{0}}^{{SF}} [ns]"
                h = ROOT.TH2F(f"dt-SF_{sipm_key}", title, nbins_pos, pos_min, pos_max, 160, -8.0, 12.0)
            elif hist_type == "dt-DS":
                title = f"{sipm_key} t_{{SiPM}} - t_{{0}}^{{DS}} vs {pos_name} (Run {run_nr});{pos_name}_{{predicted}} [cm];t_{{SiPM}} - t_{{0}}^{{DS}} [ns]"
                h = ROOT.TH2F(f"dt-DS_{sipm_key}", title, nbins_pos, pos_min, pos_max, 200, -22.0, 8.0)
            elif hist_type == "cluster_size":
                title = f"{sipm_key} Cluster Size (|residual| <= 1 mm);Cluster Hits;Clusters"
                h = ROOT.TH1F(f"cluster_size_{sipm_key}", title, 10, 0.5, 10.5)
            elif hist_type == "residual_meas":
                title = f"{sipm_key} Track-Hit Residual;Residual [mm];Hits"
                h = ROOT.TH1F(f"residual_meas_{sipm_key}", title, 100, -1.0, 1.0)
            else:
                raise ValueError(f"Unknown hist_type {hist_type}")

            h.SetDirectory(0)
            hist_cache[sipm_key][hist_type] = h
        return hist_cache[sipm_key][hist_type]

    # Pre-create all 120 SiPM keys
    for s in range(1, 6):
        for ori in ["H", "V"]:
            for m in range(3):
                for r in range(4):
                    k = f"SF{s}{ori}_{m}_{r}"
                    for ht in ["dt-SF", "dt-DS", "cluster_size", "residual_meas"]:
                        get_hist(k, ht)

    actual_entries = M.GetEntries()
    events_to_process = min(max_ev, actual_entries) if max_ev > 0 else actual_entries

    print(
        f" ~ Processing Run {run_nr} ({category}, Part {partition}): {events_to_process:,} events "
        f"[t0^SF cut: {tsf0_min:.2f} <= t0^SF <= {tsf0_max:.2f} ns, "
        f"t0^DS cut: {tds0_min:.2f} <= t0^DS <= {tds0_max:.2f} ns]",
        flush=True
    )

    t0 = time.time()
    heartbeat = 25000 if events_to_process > 50000 else 5000
    n_qualified_tracks = 0
    n_clusters_total = 0

    for n in range(events_to_process):
        if n > 0 and n % heartbeat == 0:
            rate = n / (time.time() - t0)
            print(f"   [Run {run_nr}] {n:,} / {events_to_process:,} events ({rate:.0f} ev/s, "
                  f"tracks: {n_qualified_tracks:,}, clusters: {n_clusters_total:,})...", flush=True)

        event = M.GetEvent(n)
        if len(M.Reco_MuonTracks) == 0:
            continue

        best_sf = None
        best_ds = None
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
            sx, sy = mom.x() / mom.z(), mom.y() / mom.z()
            if abs(sx) >= 0.1 or abs(sy) >= 0.1:
                continue
            ttype = trk.getTrackType() if hasattr(trk, "getTrackType") else trk.GetUniqueID()
            if ttype == 1 and best_sf is None:
                best_sf = trk
            elif ttype == 3 and best_ds is None:
                best_ds = trk

        if not best_sf:
            continue

        n_qualified_tracks += 1
        analysis.current_ds_track = best_ds

        fst = best_sf.getFittedState()
        mom = fst.getMom()
        sx, sy = mom.x() / mom.z(), mom.y() / mom.z()
        pos0 = fst.getPos()
        z0, x0, y0 = pos0.z(), pos0.x(), pos0.y()

        # Reference times
        tsf0 = analysis.GetScifiAverageTime(scifi, event.Digi_ScifiHits, mode="tsf0")
        tsf0_val = tsf0[0] if isinstance(tsf0, (tuple, list)) else tsf0
        has_valid_sf = (tsf0_val != -999. and tsf0_min <= tsf0_val <= tsf0_max)

        tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
        tds0_val = tds0[0] if isinstance(tds0, (tuple, list)) else tds0
        has_valid_ds = (tds0_val != -999. and tds0_min <= tds0_val <= tds0_max)

        if not (has_valid_sf or has_valid_ds):
            continue

        # Group hits by plane
        hits_by_plane = {}
        for h in event.Digi_ScifiHits:
            if not h.isValid():
                continue
            detID = h.GetDetectorID()
            s = detID // 1000000
            is_vert = (detID // 100000) % 10
            key = (s, is_vert)
            if key not in hits_by_plane:
                hits_by_plane[key] = []
            hits_by_plane[key].append(h)

        # Process each plane
        for (s, is_vert), z_pl in plane_z.items():
            x_trk = x0 + sx * (z_pl - z0)
            y_trk = y0 + sy * (z_pl - z0)

            pl_hits = hits_by_plane.get((s, is_vert), [])
            cluster_hits = []

            for h in pl_hits:
                detID = h.GetDetectorID()
                scifi.GetSiPMPosition(detID, A_tmp, B_tmp)
                if is_vert == 0:
                    meas_hit = (A_tmp.y() + B_tmp.y()) / 2.0
                    d_meas = abs(meas_hit - y_trk)
                    pos_pred = x_trk
                else:
                    meas_hit = (A_tmp.x() + B_tmp.x()) / 2.0
                    d_meas = abs(meas_hit - x_trk)
                    pos_pred = y_trk

                if d_meas <= 0.1:  # +/- 1 mm
                    cluster_hits.append({
                        "detID": detID,
                        "time_ns": h.GetTime() * tdc2ns,
                        "signal": h.GetSignal(),
                        "pos_pred": pos_pred,
                        "residual_mm": (meas_hit - (y_trk if is_vert == 0 else x_trk)) * 10.0
                    })

            if len(cluster_hits) > 0:
                n_clusters_total += 1
                t_sipm = min(h["time_ns"] for h in cluster_hits)
                mean_pos_pred = cluster_hits[0]["pos_pred"]
                det0 = cluster_hits[0]["detID"]
                mat_id = (det0 // 10000) % 10
                sipm_id = (det0 // 1000) % 10
                ori = "V" if is_vert else "H"
                p_key = f"SF{s}{ori}_{mat_id}_{sipm_id}"

                get_hist(p_key, "cluster_size").Fill(len(cluster_hits))
                for ch in cluster_hits:
                    get_hist(p_key, "residual_meas").Fill(ch["residual_mm"])

                if has_valid_sf:
                    dt_sf = t_sipm - tsf0_val
                    get_hist(p_key, "dt-SF").Fill(mean_pos_pred, dt_sf)

                if has_valid_ds:
                    dt_ds = t_sipm - tds0_val
                    get_hist(p_key, "dt-DS").Fill(mean_pos_pred, dt_ds)

    # Write worker histograms to temp ROOT file
    out_f = ROOT.TFile.Open(temp_output, "RECREATE")
    for pl_key, hists in hist_cache.items():
        d = out_f.mkdir(f"{category}/run{run_nr}/{pl_key}")
        d.cd()
        for h_type, h in hists.items():
            h.Write(h_type)
    out_f.Close()

    elapsed = time.time() - t0
    print(
        f" ~ [Run {run_nr} Part {partition}] Complete in {elapsed:.1f}s: "
        f"{n_qualified_tracks:,} tracks, {n_clusters_total:,} clusters -> {temp_output}",
        flush=True
    )
    os._exit(0)


def merge_temp_files(temp_files, target_path):
    """Merges partition ROOT files into the final structured ROOT file."""
    if not temp_files:
        return
    valid_files = [f for f in temp_files if os.path.exists(f) and os.path.getsize(f) > 500]
    if not valid_files:
        print("[WARNING] No non-empty temporary files to merge.")
        return

    print(f" ~ Merging {len(valid_files)} partial outputs into: {target_path}", flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)

    if os.path.exists(target_path):
        cmd = ["hadd", "-f", "-k", target_path] + valid_files
    else:
        cmd = ["hadd", "-f", target_path] + valid_files

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        print(f"[ERROR] hadd failed: {res.stderr}", file=sys.stderr)
    else:
        print(f"[SUCCESS] Merged output written to: {target_path} ({os.path.getsize(target_path):,} bytes)")


def main():
    args = parse_args()
    if not args.run_number:
        print("[ERROR] Please provide --run <run_number>", file=sys.stderr)
        sys.exit(1)

    if args.worker:
        out_f = args.temp_output or args.output_file
        run_worker(
            run_nr=int(args.run_number),
            break_events=args.break_events,
            temp_output=out_f,
            partition=args.partition,
            geo_file_override=args.geo_file,
            windows_json=args.windows_json
        )
        sys.exit(0)

    runs = [int(r.strip()) for r in args.run_number.split(",") if r.strip()]
    temp_files = []

    for run_nr in runs:
        temp_out = os.path.join(tempfile.gettempdir(), f"scifi_ref_diff_run{run_nr}_part{args.partition}_{os.getpid()}.root")
        temp_files.append(temp_out)

        pid = os.fork()
        if pid == 0:
            run_worker(
                run_nr=run_nr,
                break_events=args.break_events,
                temp_output=temp_out,
                partition=args.partition,
                geo_file_override=args.geo_file,
                windows_json=args.windows_json
            )
        else:
            _, status = os.waitpid(pid, 0)
            if os.WEXITSTATUS(status) != 0:
                print(f"[ERROR] Worker for Run {run_nr} failed with exit code {os.WEXITSTATUS(status)}", file=sys.stderr)

    merge_temp_files(temp_files, args.output_file)
    for f in temp_files:
        if os.path.exists(f):
            try:
                os.remove(f)
            except OSError:
                pass


if __name__ == "__main__":
    main()
