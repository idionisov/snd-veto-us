#!/usr/bin/env python3
"""
sipm_ref_diff.py
----------------
Extracts the difference between reference times and SiPM readout time:
  t0^DS - t_SiPM  and  t0^SF - t_SiPM
for each channel (detectorID_SiPMnum: XXXXX_Y) in the Veto and Upstream systems.

Selection logic:
  - Upstream bars (system 2, detID 20000..24009):
      ALWAYS crossed by a qualified DS track (reconstructed DS track,
      chi2ndf < 5, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad).
  - Veto bars (system 1, detID 10000..11006):
      ALWAYS crossed by a qualified SciFi track (reconstructed SciFi track,
      chi2ndf < 5, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad).

t_SiPM = clock * TDC2ns.
Reference time cut on t0^DS:
  - Category I   (run <= 5116 and 5175 <= run <= 5192) : 20.25 <= t0^DS <= 24.15 ns
  - Category II  (5117 <= run <= 5174 and 5193 <= run <= 5412) : 13.0 <= t0^DS <= 15.5 ns
  - Category III (all other cases)                      : 18.5 <= t0^DS <= 20.5 ns
Reference time cut on t0^SF:
  - All Categories                                      : -0.5 <= t0^SF <= 6.0 ns

Output ROOT File Structure:
  <catI | catII | catIII>/runXXXX/<detID_SiPM>/
    ├── dt-DS   (t0^DS - t_SiPM)
    └── dt-SF   (t0^SF - t_SiPM)
"""

import os
import sys
import tempfile
import argparse
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        return 20.25, 24.15
    elif cat == "catII":
        return 13.0, 15.5
    else:
        return 18.5, 20.5


def get_tsf0_window(run_nr=None):
    """Returns (tsf0_min, tsf0_max) window for SciFi reference time."""
    return -0.5, 6.0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract t0^DS - t_SiPM and t0^SF - t_SiPM distributions for each SiPM channel."
    )
    parser.add_argument(
        "-r", "--run", "--run-number",
        dest="run_number",
        type=str,
        default=None,
        help="Run number or comma-separated list of runs to process (default: all qualifying 2022 runs)"
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
        default="/eos/user/i/idioniso/Timing/sipm_ref_diff_2022.root",
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


def run_worker(run_nr, break_events, temp_output, partition=-1, geo_file_override=None):
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

    # 1. Resolve dataset via DataManager
    dm = DataManager(run=run_nr)

    # 2. Resolve geometry file
    if geo_file_override:
        geo_file = geo_file_override
    else:
        geo_file = dm.get_geo_path()
        if not geo_file:
            geo_file = DataManager.get_geo_path_for_run(run_nr)

    # 3. Configure server and paths
    server = os.environ.get("EOSSHIP", "root://eospublic.cern.ch/")
    if not server.endswith("/"):
        server += "/"

    data_path = dm.data_base_path or "/eos/experiment/sndlhc/convertedData/physics/2022/"
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

    # Pre-fetch geometry references
    nav = ROOT.gGeoManager.GetCurrentNavigator()
    mu_filter = M.MuFilter
    tdc2ns = analysis.TDC2ns
    tds0_min, tds0_max = get_tds0_window(run_nr)
    tsf0_min, tsf0_max = get_tsf0_window(run_nr)
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

    # Histogram cache: channel_key -> {'dt-DS': TH2F, 'dt-SF': TH2F}
    hist_cache = {}

    def get_hist(channel_key, hist_type):
        if channel_key not in hist_cache:
            hist_cache[channel_key] = {}
        if hist_type not in hist_cache[channel_key]:
            det_id = int(channel_key.split("_")[0])
            subsys = det_id // 10000

            if subsys == 1:
                # Veto: bar extent ~ [-48, -7] cm
                # x range: (-53, -7) with 1 cm bins (46 bins)
                # y range: (-27.5, 27.5) with 0.25 ns bins (220 bins)
                nbins_x, x_min, x_max = 46, -53.0, -7.0
                nbins_y, y_min, y_max = 220, -27.5, 27.5
            else:
                # Upstream: bar extent ~ [-79, +3] cm
                # x range: (-60, 0) with 1 cm bins (60 bins)
                # y range: (-27.5, 27.5) with 0.25 ns bins (220 bins)
                nbins_x, x_min, x_max = 60, -60.0, 0.0
                nbins_y, y_min, y_max = 220, -27.5, 27.5

            if hist_type == "dt-DS":
                title = f"{channel_key} t_{{0}}^{{DS}} - t_{{SiPM}} vs x-position (Run {run_nr});x_{{predicted}} [cm];t_{{0}}^{{DS}} - t_{{SiPM}} [ns]"
                h = ROOT.TH2F(f"dt-DS_{channel_key}", title, nbins_x, x_min, x_max, nbins_y, y_min, y_max)
            else:
                title = f"{channel_key} t_{{0}}^{{SF}} - t_{{SiPM}} vs x-position (Run {run_nr});x_{{predicted}} [cm];t_{{0}}^{{SF}} - t_{{SiPM}} [ns]"
                h = ROOT.TH2F(f"dt-SF_{channel_key}", title, nbins_x, x_min, x_max, nbins_y, y_min, y_max)
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

    def passes_fiducial(det_id, x_ex, y_ex, cut=5.0):
        a_pt, b_pt = ROOT.TVector3(), ROOT.TVector3()
        mu_filter.GetPosition(det_id, a_pt, b_pt)
        subsys, pl, _ = analysis.parseDetID(det_id)
        if subsys == 1 and pl == 2:
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

        # 2. Extract DS Reference Time and apply category window cut
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

        # 3. Extract SciFi Reference Time and apply category window cut (-0.5 <= t0^SF <= 6.0 ns)
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

        # 4. Predict crossed bars:
        #    - Upstream planes crossed by DS track
        expected_us_bars = {}
        if best_ds:
            pos_ds = best_ds["pos"]
            mom_ds = best_ds["mom"]
            n_us_planes = M.systemAndPlanes.get(2, 5)
            for plane in range(n_us_planes):
                z_key = 20 + plane
                if z_key not in M.zPos["MuFilter"]:
                    continue
                zEx = M.zPos["MuFilter"][z_key]
                lam = (zEx - pos_ds.z()) / mom_ds.z()
                xEx = pos_ds.x() + lam * mom_ds.x()
                yEx = pos_ds.y() + lam * mom_ds.y()
                node = nav.FindNode(xEx, yEx, zEx)
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
            n_veto_planes = M.systemAndPlanes.get(1, 2)
            for plane in range(n_veto_planes):
                z_key = 10 + plane
                if z_key not in M.zPos["MuFilter"]:
                    continue
                zEx = M.zPos["MuFilter"][z_key]
                lam = (zEx - pos_sf.z()) / mom_sf.z()
                xEx = pos_sf.x() + lam * mom_sf.x()
                yEx = pos_sf.y() + lam * mom_sf.y()
                node = nav.FindNode(xEx, yEx, zEx)
                if node:
                    node_name = node.GetName()
                    if node_name.startswith("volVetoBar_") or node_name.startswith("volVetoBar_ver_"):
                        try:
                            bar_det_id = int(node_name.split("_")[-1])
                            if passes_fiducial(bar_det_id, xEx, yEx):
                                expected_veto_bars[plane] = (bar_det_id, xEx)
                        except ValueError:
                            pass

        # 5. Loop over Digi_MuFilterHits for both Veto (s == 1) and Upstream (s == 2)
        for hit in event.Digi_MuFilterHits:
            if not hit.isValid():
                continue
            detID = hit.GetDetectorID()
            s, p, b = analysis.parseDetID(detID)

            # Upstream bars (s == 2): ALWAYS use DS track
            if s == 2:
                if not best_ds or p not in expected_us_bars or expected_us_bars[p][0] != detID:
                    continue
                x_pred = expected_us_bars[p][1]

            # Veto bars (s == 1): ALWAYS use SciFi track
            elif s == 1:
                if not best_sf or p not in expected_veto_bars or expected_veto_bars[p][0] != detID:
                    continue
                x_pred = expected_veto_bars[p][1]

            else:
                continue

            channels_t = hit.GetAllTimes()
            signals_dict = dict(hit.GetAllSignals())
            for item in channels_t:
                sipm_num, clock = item
                if sipm_num < 0 or sipm_num > 15:
                    continue

                # Drop small SiPMs in US
                if s == 2 and analysis.IsSmallSiPMchannel(sipm_num):
                    continue

                # For vertical veto bars (subsystem 1, plane 2, detID >= 12000), readout is top side only (0..7)
                if s == 1 and p == 2 and sipm_num >= 8:
                    continue

                # Skip known dead channel
                if f"{detID}_{sipm_num}" == "21005_15":
                    continue

                # Require valid positive QDC signal above threshold (matching TimeWalk.py)
                qdc = signals_dict.get(sipm_num, -999.)
                if qdc == -999. or qdc <= 0:
                    continue

                t_sipm = clock * tdc2ns
                ch_key = f"{detID}_{sipm_num}"

                if has_valid_ds:
                    dt_ds = tds0_val - t_sipm
                    get_hist(ch_key, "dt-DS").Fill(x_pred, dt_ds)

                if has_valid_sf:
                    dt_sf = tsf0_val - t_sipm
                    get_hist(ch_key, "dt-SF").Fill(x_pred, dt_sf)

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

    print(f" ~ Run {run_nr} ({category}) complete: filled {len(hist_cache)} SiPM channels.", flush=True)
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
            geo_file_override=args.geo_file
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
    print(" SND@LHC SiPM vs Reference Time Difference Extraction Pipeline")
    print(f" Target ROOT File  : {out_root_path}")
    print(f" Break Event Limit : {args.break_events:,} events/run (0 = full run)")
    print(f" Number of Runs    : {len(runs_to_process)}")
    print(f" Parallel Workers  : {args.n_workers} processes")
    print(" Reference Cut: Category-dependent t0^DS window & t0^SF window (-0.5, 6.0 ns) applied")
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
            if args.geo_file:
                worker_cmd.extend(["-g", args.geo_file])

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
                h_ds = ch_dir.Get("dt-DS")
                if h_ds:
                    h_ds.SetDirectory(0)
                    channels_data[ch_name]["dt-DS"] = h_ds
                h_sf = ch_dir.Get("dt-SF")
                if h_sf:
                    h_sf.SetDirectory(0)
                    channels_data[ch_name]["dt-SF"] = h_sf

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
                    if "dt-DS" in h_dict:
                        h_dict["dt-DS"].Write("dt-DS", ROOT.TObject.kOverwrite)
                    if "dt-SF" in h_dict:
                        h_dict["dt-SF"].Write("dt-SF", ROOT.TObject.kOverwrite)

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
