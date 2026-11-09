#!/usr/bin/env python3
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import argparse
import ROOT
import Monitor
import SndlhcTracking
import python.AnalysisFunctions as af
from snd import DataManager

def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract SciFi and DS reference times from SND@LHC data"
    )
    parser.add_argument(
        "-i", "--input",
        dest="input_path",
        type=str,
        default=None,
        help="Full input filepath (wildcards allowed). If provided, it is always used."
    )
    parser.add_argument(
        "-r", "--run-number",
        dest="run_number",
        type=int,
        default=5408,
        help="Run number to load via DataManager (default: 5408)"
    )
    parser.add_argument(
        "-g", "--geofile",
        dest="geo_file",
        type=str,
        default=None,
        help="Forcefully load the provided geofile. If omitted, adapts from the lookup table."
    )
    parser.add_argument(
        "-o", "--output",
        dest="output_file",
        type=str,
        default=None,
        help="Output ROOT file to store histograms."
    )
    parser.add_argument(
        "-n", "--n-events",
        dest="n_events",
        type=int,
        default=50000,
        help="Maximum number of events to process (default: 50000)"
    )
    parser.add_argument(
        "-P", "--partition",
        dest="partition",
        type=int,
        default=-1,
        help="Data partition number (default: -1 for all partitions)"
    )
    return parser.parse_args()

def main():
    args = parse_args()

    # 1. Resolve dataset via DataManager
    if args.input_path:
        dm = DataManager(args.input_path)
        run_nr = dm.run_number if dm.run_number is not None else args.run_number
    else:
        run_nr = args.run_number
        dm = DataManager.from_run(run_nr, n_files=-1)

    # 2. Resolve geometry file
    if args.geo_file:
        geo_file = args.geo_file
    else:
        geo_file = dm.get_geo_path()
        if not geo_file:
            geo_file = DataManager.get_geo_path_for_run(run_nr)

    # 3. Configure Monitor options
    server = os.environ.get("EOSSHIP", "root://eospublic.cern.ch/")
    if not server.endswith("/"):
        server += "/"

    data_path = dm.data_base_path or ""
    if data_path.startswith(server):
        data_path = data_path[len(server):]
    elif data_path.startswith("root://eospublic.cern.ch/"):
        data_path = data_path[len("root://eospublic.cern.ch/"):]

    if geo_file.startswith(server) or geo_file.startswith("root://"):
        geo_file_opt = "../" + geo_file
    else:
        geo_file_opt = geo_file

    options = type("Opts", (), {
        "runNumber": run_nr,
        "numuStudy": False,
        "nueStudy": False,
        "state": "raw",
        "CorrectionType": "DS",
        "referencesystem": 3,  # 3 = DS, 1 = SF
        "datalocation": "physics",
        "simulation": False,
        "geoFile": geo_file_opt,
        "path": data_path,
        "server": server,
        "online": False,
        "fname": dm.files[0] if (args.input_path and len(dm.files) == 1) else None,
        "partition": args.partition,
        "interactive": False,
        "saveTo": "",
        "nStart": 0,
        "nEvents": args.n_events,
        "trackType": "ScifiDS",
    })()
    analysis = af.Analysis(options)

    # Histograms
    h_tds0 = ROOT.TH1F("h_tds0", "DS Reference Time t_{0}^{DS};t_{0}^{DS} [ns];Counts", 200, 0, 50)
    h_tsf0 = ROOT.TH1F("h_tsf0", "SciFi Reference Time t_{0}^{SF};t_{0}^{SF} [ns];Counts", 200, -25, 25)
    h_scifi_ds = ROOT.TH2F(
        "h_scifi_ds",
        "SciFi vs DS Reference Time;t_{0}^{SF} [ns];t_{0}^{DS} [ns]",
        200, -25, 25,
        200, 0, 50
    )
    h_delta_t = ROOT.TH1F(
        "h_delta_t",
        "#Delta t (t_{0}^{DS} - t_{0}^{SF});t_{0}^{DS} - t_{0}^{SF} [ns];Counts",
        200, 0, 50
    )

    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")
    FairTasks = [track_task]
    M = Monitor.Monitoring(options, FairTasks)
    M.M = M  # AnalysisFunctions expects task.M.Reco_MuonTracks
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

    total_events = min(args.n_events, M.GetEntries()) if args.n_events > 0 else M.GetEntries()

    for n in range(total_events):
        event = M.GetEvent(n)

        # 1. Require single reconstructed track with quality cuts
        if M.Reco_MuonTracks.GetEntries() != 1:
            continue
        track = M.Reco_MuonTracks[0]
        fitState = track.getFittedState()
        mom = fitState.getMom()
        if abs(mom.x() / mom.z()) > 0.1 or abs(mom.y() / mom.z()) > 0.1:
            continue

        # 2. Extract DS Reference Time (mode='tds0')
        tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
        has_ds = (tds0 != -999.)
        tds0_val = tds0[0] if has_ds else None

        # 3. Extract SciFi Reference Time (mode='tsf0')
        tsf0 = analysis.GetScifiAverageTime(M.Scifi, event.Digi_ScifiHits, mode="tsf0")
        has_sf = (tsf0 != -999.)

        if has_ds:
            h_tds0.Fill(tds0_val)
        if has_sf:
            h_tsf0.Fill(tsf0)

        # 4. Joint reference times (both SciFi and DS available)
        if has_ds and has_sf:
            h_scifi_ds.Fill(tsf0, tds0_val)
            h_delta_t.Fill(tds0_val - tsf0)

    # Output ROOT file
    out_root_path = args.output_file if args.output_file else f"reftimes_run{run_nr}.root"
    out_root = ROOT.TFile.Open(out_root_path, "RECREATE")
    h_tds0.Write()
    h_tsf0.Write()
    h_scifi_ds.Write()
    h_delta_t.Write()
    out_root.Close()
    print(f"Histograms saved to {out_root_path}")

    # Plot summary canvas
    c = ROOT.TCanvas("c", "Reference Times", 1600, 500)
    c.Divide(3, 1)
    c.cd(1); h_tds0.Draw()
    c.cd(2); h_tsf0.Draw()
    c.cd(3); h_scifi_ds.Draw("COLZ")
    png_path = f"reftimes_run{run_nr}.png"
    c.SaveAs(png_path)
    print(f"Canvas plot saved to {png_path}")
    print(f"Summary: TDS0 entries={h_tds0.GetEntries():.0f}, TSF0 entries={h_tsf0.GetEntries():.0f}, Joint entries={h_scifi_ds.GetEntries():.0f}")

    # Immediate clean exit to avoid FairRoot/XRootD shutdown freeze
    os._exit(0)

if __name__ == "__main__":
    main()
