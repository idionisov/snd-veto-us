#!/usr/bin/env python3
"""
ref_times.py
------------
Extracts SciFi and DS reference times (reft-SF and reft-DS) for runs from runs_2022.csv
(Categories I and II, >3M entries, nonzero luminosity, is_physics_collision == True).

Outputs a single ROOT file organized as:
  <catI | catII>/runXXXX/
    ├── reft-DS
    └── reft-SF

Inputs are loaded automatically via DataManager given a -r argument.
Includes a --break argument (default 10,000,000 events) to break when reaching the limit.
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

import ROOT


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract SciFi and DS reference times from SND@LHC data"
    )
    parser.add_argument(
        "-r", "--run", "--run-number",
        dest="run_number",
        type=str,
        default=None,
        help="Run number or comma-separated list of runs to process (default: all qualifying 2022 Cat I/II runs)"
    )
    parser.add_argument(
        "-b", "--break", "--break-events", "-n",
        dest="break_events",
        type=int,
        default=10000000,
        help="Break processing if processed events exceed this number (default: 10,000,000; set <=0 for full run)"
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
        default="/eos/user/i/idioniso/Timing/reference_times_2022.root",
        help="Single output ROOT file storing catI and catII directories (default: /eos/user/i/idioniso/Timing/reference_times_2022.root)"
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
    """Processes a single run in an isolated subprocess to ensure clean FairRoot initialization."""
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
        "saveTo": os.path.dirname(os.path.abspath(temp_output)) if temp_output else "/tmp",
        "nStart": 0,
        "nEvents": max_ev,
        "trackType": "ScifiDS",
    })()

    analysis = af.Analysis(options)

    # Output histograms
    h_tds0 = ROOT.TH1F("reft-DS", f"DS Reference Time (Run {run_nr});t_{{0}}^{{DS}} [ns];Counts", 200, 0, 50)
    h_tsf0 = ROOT.TH1F("reft-SF", f"SciFi Reference Time (Run {run_nr});t_{{0}}^{{SF}} [ns];Counts", 200, -25, 25)

    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")
    FairTasks = [track_task]
    M = Monitor.Monitoring(options, FairTasks)
    M.M = M
    analysis.SetTask(M)

    # Monkey-patch GetDSHaverage to safely ignore non-DS measurements from ScifiDS tracks
    orig_GetDSHaverage = af.Analysis.GetDSHaverage

    def safe_GetDSHaverage(self, hits, mode="tds0"):
        if mode == "tds0":
            stations = {i.GetDetectorID(): i for i in hits}
            total = {i: 0 for i in range(4)}
            counter = {i: 0 for i in range(4)}
            theTrack = self.task.M.Reco_MuonTracks[0]
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

    actual_entries = M.GetEntries()
    events_to_process = min(max_ev, actual_entries) if max_ev > 0 else actual_entries

    print(f" ~ Processing Run {run_nr}: {events_to_process:,} events (break limit: {break_events:,}, total in run: {actual_entries:,})", flush=True)

    heartbeat = 50000
    for n in range(events_to_process):
        if n > 0 and n % heartbeat == 0:
            print(f"   [Run {run_nr}] Event {n:,} / {events_to_process:,} "
                  f"(reft-DS: {h_tds0.GetEntries():,.0f}, reft-SF: {h_tsf0.GetEntries():,.0f})", flush=True)

        event = M.GetEvent(n)

        # 1. Require single reconstructed track with quality cuts
        if M.Reco_MuonTracks.GetEntries() != 1:
            continue
        track = M.Reco_MuonTracks[0]
        fitState = track.getFittedState()
        mom = fitState.getMom()
        if abs(mom.x() / mom.z()) > 0.1 or abs(mom.y() / mom.z()) > 0.1:
            continue

        # 2. Extract DS Reference Time
        tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
        has_ds = False
        if isinstance(tds0, (tuple, list)):
            if tds0[0] != -999.:
                tds0_val = tds0[0]
                has_ds = True
        elif tds0 != -999.:
            tds0_val = tds0
            has_ds = True

        # 3. Extract SciFi Reference Time
        tsf0 = analysis.GetScifiAverageTime(M.Scifi, event.Digi_ScifiHits, mode="tsf0")
        has_sf = (tsf0 != -999.)

        if has_ds:
            h_tds0.Fill(tds0_val)
        if has_sf:
            h_tsf0.Fill(tsf0)

    # Write worker histograms to temp file
    out_f = ROOT.TFile.Open(temp_output, "RECREATE")
    h_tds0.Write("reft-DS")
    h_tsf0.Write("reft-SF")
    out_f.Close()

    print(f" ~ Run {run_nr} complete: reft-DS={h_tds0.GetEntries():,.0f}, reft-SF={h_tsf0.GetEntries():,.0f}", flush=True)
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

    def norm_cat(c):
        c_str = str(c).strip().upper()
        if c_str in ("I", "CATI"):
            return "catI"
        if c_str in ("II", "CATII"):
            return "catII"
        return None

    df["cat_norm"] = df["category"].apply(norm_cat)

    if args.run_number:
        run_list = [int(x.strip()) for x in str(args.run_number).split(",") if x.strip()]
        runs_to_process = []
        for r in run_list:
            row = df[df["run_number"] == r]
            if not row.empty and row["cat_norm"].values[0]:
                cat = row["cat_norm"].values[0]
            else:
                cat = "catI"
            runs_to_process.append((r, cat))
    else:
        mask = (
            df["cat_norm"].isin(["catI", "catII"]) &
            (df["entries"] > 3000000) &
            (df["luminosity_pb"] > 0) &
            (df["is_physics_collision"] == True)
        )
        filtered_df = df[mask].sort_values("run_number")
        runs_to_process = [(int(row["run_number"]), row["cat_norm"]) for _, row in filtered_df.iterrows()]
        print(f"Loaded {len(runs_to_process)} qualifying runs from {csv_path} (Category I & II, >3M entries, lumi > 0, is_physics_collision==True).")

    out_root_path = args.output_file
    out_dir = os.path.dirname(os.path.abspath(out_root_path))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    print("======================================================================")
    print(" SND@LHC Reference Time Extraction Pipeline")
    print(f" Target ROOT File  : {out_root_path}")
    print(f" Break Event Limit : {args.break_events:,} events/run (0 = full run)")
    print(f" Number of Runs    : {len(runs_to_process)}")

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
                        if r_dir and r_dir.Get("reft-DS") and r_dir.Get("reft-SF"):
                            ds_n = r_dir.Get("reft-DS").GetEntries()
                            sf_n = r_dir.Get("reft-SF").GetEntries()
                            chk_f.Close()
                            print(f"[{idx}/{len(runs_to_process)}] Skipping {cat}/{run_dir_name} (already exists: DS={ds_n:,.0f}, SF={sf_n:,.0f})", flush=True)
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
            h_ds = f_temp.Get("reft-DS")
            h_sf = f_temp.Get("reft-SF")

            if not h_ds or not h_sf:
                print(f"[ERROR] Could not extract histograms from worker output for Run {r}.", file=sys.stderr, flush=True)
                f_temp.Close()
                return False

            h_ds.SetDirectory(0)
            h_sf.SetDirectory(0)
            ds_entries = h_ds.GetEntries()
            sf_entries = h_sf.GetEntries()
            f_temp.Close()

            with file_lock:
                f_master = ROOT.TFile.Open(out_root_path, "UPDATE")
                cat_dir = f_master.GetDirectory(cat)
                if not cat_dir:
                    cat_dir = f_master.mkdir(cat)
                cat_dir.cd()

                r_dir = cat_dir.GetDirectory(run_dir_name)
                if not r_dir:
                    r_dir = cat_dir.mkdir(run_dir_name)
                r_dir.cd()

                h_ds.Write("reft-DS", ROOT.TObject.kOverwrite)
                h_sf.Write("reft-SF", ROOT.TObject.kOverwrite)
                f_master.Close()

            print(f"[{idx}/{len(runs_to_process)}] [SUCCESS] Stored {cat}/{run_dir_name}/[reft-DS, reft-SF] into {out_root_path} (DS: {ds_entries:,.0f}, SF: {sf_entries:,.0f})", flush=True)
            return True

        finally:
            if os.path.exists(temp_output):
                os.remove(temp_output)

    # Dispatch parallel workers
    n_workers = min(args.n_workers, len(runs_to_process)) if args.n_workers > 0 else 1
    print(f" Parallel Workers  : {n_workers} processes")
    print("======================================================================")

    indexed_runs = list(enumerate(runs_to_process, 1))

    if n_workers <= 1:
        for item in indexed_runs:
            process_run(item)
    else:
        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            futures = [executor.submit(process_run, item) for item in indexed_runs]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    print(f"[EXCEPTION] Run worker failed: {e}", file=sys.stderr, flush=True)

    print("\n======================================================================")
    print(f"[FINISHED] All requested runs processed. Output saved to: {out_root_path}")
    print("======================================================================")


if __name__ == "__main__":
    main()
