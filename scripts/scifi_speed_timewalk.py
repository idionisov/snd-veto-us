#!/usr/bin/env python3
"""
scifi_speed_timewalk.py
-----------------------
Extracts the effective speed of light (c_fiber) and tests for timewalk effects
in the SciFi fiber tracker using reconstructed SciFi tracks and reference times:
  - t_cluster - t0^SF - ToF_mu  vs  L_prop
  - t_cluster - t0^DS - ToF_mu  vs  L_prop
  - t_cluster - t0^SF - ToF_mu  vs  QDC (Total & Peak)

Selection cuts:
  - Pre-selection (applied BEFORE track reconstruction):
      1 <= nVetoHits <= 3  and  6 <= nScifiHits < 27
  - SciFi Track quality:
      Reconstructed SciFi track (track_type == 1)
      chi2ndf < 5.0, |slope_x| < 0.1 rad, |slope_y| < 0.1 rad
  - Cluster formation:
      SciFi hits within +/- 1 mm (|d| <= 0.1 cm) of the extrapolated track in measuring plane:
        * Horizontal planes: |y_hit - y_track| <= 0.1 cm
        * Vertical planes:   |x_hit - x_track| <= 0.1 cm
  - Propagation distance along the fiber:
        * Horizontal planes (readout on left):  L_prop = |x_track - A_x|
        * Vertical planes   (readout on top):   L_prop = |B_y - y_track|

Output ROOT structure:
  scifi/
    ├── station{1..5}_{H,V}/
    │     ├── dt_SF_vs_L
    │     ├── dt_DS_vs_L
    │     ├── dt_SF_vs_Qtot
    │     ├── dt_SF_vs_Qmax
    │     ├── cluster_size
    │     └── residual_meas
    └── inclusive/
          ├── dt_SF_vs_L
          ├── dt_DS_vs_L
          ├── dt_SF_vs_Qtot
          ├── dt_SF_vs_Qmax
          ├── cluster_size
          └── residual_meas
"""

import os
import sys
import json
import time
import argparse
import numpy as np

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
        description="Extract SciFi effective speed of light and analyze timewalk effect."
    )
    parser.add_argument(
        "-r", "--run", "--run-number",
        dest="run_number",
        type=int,
        required=True,
        help="Run number to process"
    )
    parser.add_argument(
        "-p", "--partition",
        type=int,
        default=0,
        help="Partition number to process (-1 for all partitions, default: 0)"
    )
    parser.add_argument(
        "-n", "--max-events",
        type=int,
        default=-1,
        help="Maximum events to process (-1 for full partition, default: -1)"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output ROOT file path (default: /tmp/scifi_speed_run<RUN>_part<PART>.root)"
    )
    parser.add_argument(
        "--geo",
        type=str,
        default=None,
        help="Custom geometry file override"
    )
    parser.add_argument(
        "--windows-json",
        type=str,
        default=None,
        help="Path to ref_time_windows.json"
    )
    parser.add_argument(
        "--plot",
        action="store_true",
        help="Generate summary matplotlib diagnostic figure"
    )
    parser.add_argument(
        "--plot-output",
        type=str,
        default=None,
        help="Custom output image path for plot"
    )
    return parser.parse_args()


def run_analysis(run_nr, partition=0, max_events=-1, output_path=None, geo_file_override=None,
                 windows_json=None, make_plot=False, plot_output=None):
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

    # 1. Resolve dataset and geometry paths
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

    if output_path is None:
        output_path = f"/tmp/scifi_speed_run{run_nr}_part{partition}.root"
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

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
        "saveTo": "/tmp",
        "nStart": 0,
        "nEvents": max_events if max_events > 0 else -1,
        "trackType": "ScifiDS",
    })()

    # Pre-selection optimization: hook track_task.ExecuteTask to ONLY execute on preselected events
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

    # Calculate plane z positions and first station z for muon ToF correction
    plane_z = {}
    A_tmp, B_tmp = ROOT.TVector3(), ROOT.TVector3()
    for s in range(1, 6):
        scifi.GetSiPMPosition(s * 1000000, A_tmp, B_tmp)
        plane_z[(s, 0)] = (A_tmp.z() + B_tmp.z()) / 2.0
        scifi.GetSiPMPosition(s * 1000000 + 100000, A_tmp, B_tmp)
        plane_z[(s, 1)] = (A_tmp.z() + B_tmp.z()) / 2.0

    z_station1 = plane_z.get((1, 0), 300.0)

    # Book ROOT histograms
    histograms = {}

    def book_hists(prefix, title_suffix):
        return {
            "dt_SF_vs_L": ROOT.TH2F(
                f"{prefix}_dt_SF_vs_L",
                f"Cluster Time - t_{{0}}^{{SF}} vs Propagation Distance {title_suffix};L_{{prop}} [cm];t_{{cluster}} - t_{{0}}^{{SF}} - ToF [ns]",
                50, 0.0, 45.0, 160, -8.0, 12.0
            ),
            "dt_DS_vs_L": ROOT.TH2F(
                f"{prefix}_dt_DS_vs_L",
                f"Cluster Time - t_{{0}}^{{DS}} vs Propagation Distance {title_suffix};L_{{prop}} [cm];t_{{cluster}} - t_{{0}}^{{DS}} - ToF [ns]",
                50, 0.0, 45.0, 200, -20.0, 10.0
            ),
            "dt_SF_vs_Qtot": ROOT.TH2F(
                f"{prefix}_dt_SF_vs_Qtot",
                f"Cluster Time - t_{{0}}^{{SF}} vs Total QDC {title_suffix};Cluster Total QDC;t_{{cluster}} - t_{{0}}^{{SF}} - ToF [ns]",
                60, -2.0, 18.0, 160, -8.0, 12.0
            ),
            "dt_SF_vs_Qmax": ROOT.TH2F(
                f"{prefix}_dt_SF_vs_Qmax",
                f"Cluster Time - t_{{0}}^{{SF}} vs Peak Hit QDC {title_suffix};Peak Hit QDC;t_{{cluster}} - t_{{0}}^{{SF}} - ToF [ns]",
                60, -2.0, 14.0, 160, -8.0, 12.0
            ),
            "cluster_size": ROOT.TH1F(
                f"{prefix}_cluster_size",
                f"Cluster Size (|d| <= 1 mm) {title_suffix};Number of Hits in Cluster;Clusters",
                10, 0.5, 10.5
            ),
            "residual_meas": ROOT.TH1F(
                f"{prefix}_residual_meas",
                f"Track-Hit Residual {title_suffix};Residual [mm];Hits",
                100, -1.0, 1.0
            )
        }

    histograms["inclusive"] = book_hists("inc", "(Inclusive)")
    for s in range(1, 6):
        for is_v in (0, 1):
            pl_tag = "V" if is_v else "H"
            histograms[(s, is_v)] = book_hists(f"s{s}{pl_tag}", f"(Station {s} {pl_tag})")

    # Arrays for matplotlib plotting if requested
    plot_data = {
        "dt_sf": [], "dt_ds": [], "L": [], "q_tot": [], "q_max": []
    }

    actual_entries = M.GetEntries()
    events_to_process = min(max_events, actual_entries) if max_events > 0 else actual_entries

    print(
        f" ~ Processing Run {run_nr} (Part {partition}): {events_to_process:,} events "
        f"[t0^SF window: {tsf0_min:.2f}..{tsf0_max:.2f} ns, t0^DS window: {tds0_min:.2f}..{tds0_max:.2f} ns]",
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

        # Loop over all 10 SciFi planes
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
                    L_prop = abs(x_trk - A_tmp.x())
                else:
                    meas_hit = (A_tmp.x() + B_tmp.x()) / 2.0
                    d_meas = abs(meas_hit - x_trk)
                    L_prop = abs(B_tmp.y() - y_trk)

                if d_meas <= 0.1:  # +/- 1 mm
                    cluster_hits.append({
                        "detID": detID,
                        "time_ns": h.GetTime() * tdc2ns,
                        "signal": h.GetSignal(),
                        "L_prop": L_prop,
                        "residual_mm": (meas_hit - (y_trk if is_vert == 0 else x_trk)) * 10.0
                    })

            if len(cluster_hits) > 0:
                n_clusters_total += 1
                t_earliest = min(h["time_ns"] for h in cluster_hits)
                total_q = sum(h["signal"] for h in cluster_hits)
                max_q = max(h["signal"] for h in cluster_hits)
                mean_L = sum(h["L_prop"] for h in cluster_hits) / len(cluster_hits)

                # Muon flight time from first station
                tof_mu = (z_pl - z_station1) / 29.979  # in ns

                dt_sf = (t_earliest - tsf0_val - tof_mu) if has_valid_sf else None
                dt_ds = (t_earliest - tds0_val - tof_mu) if has_valid_ds else None

                target_dicts = [histograms["inclusive"], histograms[(s, is_vert)]]
                for hd in target_dicts:
                    hd["cluster_size"].Fill(len(cluster_hits))
                    for ch in cluster_hits:
                        hd["residual_meas"].Fill(ch["residual_mm"])
                    if dt_sf is not None:
                        hd["dt_SF_vs_L"].Fill(mean_L, dt_sf)
                        hd["dt_SF_vs_Qtot"].Fill(total_q, dt_sf)
                        hd["dt_SF_vs_Qmax"].Fill(max_q, dt_sf)
                    if dt_ds is not None:
                        hd["dt_DS_vs_L"].Fill(mean_L, dt_ds)

                if make_plot:
                    plot_data["dt_sf"].append(dt_sf)
                    plot_data["dt_ds"].append(dt_ds)
                    plot_data["L"].append(mean_L)
                    plot_data["q_tot"].append(total_q)
                    plot_data["q_max"].append(max_q)

    # 5. Write to ROOT file
    out_f = ROOT.TFile.Open(output_path, "RECREATE")
    for key, hd in histograms.items():
        if key == "inclusive":
            d_name = "inclusive"
        else:
            s, is_v = key
            d_name = f"station{s}_{'V' if is_v else 'H'}"
        d = out_f.mkdir(d_name)
        d.cd()
        for h in hd.values():
            h.Write()
    out_f.Close()

    elapsed = time.time() - t0
    print(f"\n======================================================================")
    print(f"  SCIFI SPEED & TIMEWALK ANALYSIS COMPLETE (Run {run_nr}, Part {partition})")
    print(f"======================================================================")
    print(f"  Events Processed    : {events_to_process:,}")
    print(f"  Qualified SciFi Trks: {n_qualified_tracks:,}")
    print(f"  Total Clusters      : {n_clusters_total:,}")
    print(f"  Elapsed Time        : {elapsed:.2f}s ({events_to_process/elapsed:.0f} ev/s)")
    print(f"  Output ROOT File    : {output_path}")
    print(f"======================================================================\n", flush=True)

    # Optional matplotlib plotting
    if make_plot and len(plot_data["L"]) > 0:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, axes = plt.subplots(2, 2, figsize=(14, 11))

        valid_sf = np.array([x is not None for x in plot_data["dt_sf"]])
        sf_dts = np.array([x for x in plot_data["dt_sf"] if x is not None])
        sf_Ls = np.array(plot_data["L"])[valid_sf]
        sf_qs = np.array(plot_data["q_tot"])[valid_sf]
        sf_qmaxs = np.array(plot_data["q_max"])[valid_sf]

        # 1. dt vs Qtot
        ax1 = axes[0, 0]
        h1 = ax1.hist2d(sf_qs, sf_dts, bins=[60, 80], range=[[-2, 18], [-5, 10]], cmap="Blues", cmin=1)
        ax1.set_xlabel("Cluster Total QDC", fontsize=12)
        ax1.set_ylabel(r"$t_{cluster} - t_0^{SF} - \mathrm{ToF}_\mu$ [ns]", fontsize=12)
        ax1.set_title("Timewalk Test: Cluster Time vs Total QDC", fontsize=13, fontweight="bold")
        ax1.grid(True, linestyle="--", alpha=0.5)
        fig.colorbar(h1[3], ax=ax1, label="Counts")

        q_bins = np.linspace(-1, 15, 17)
        bin_c = (q_bins[:-1] + q_bins[1:]) / 2.0
        p_m, p_s = [], []
        for ql, qh in zip(q_bins[:-1], q_bins[1:]):
            m = (sf_qs >= ql) & (sf_qs < qh) & (sf_dts >= -5) & (sf_dts <= 10)
            if np.sum(m) > 10:
                p_m.append(np.mean(sf_dts[m]))
                p_s.append(np.std(sf_dts[m]) / np.sqrt(np.sum(m)))
            else:
                p_m.append(np.nan)
                p_s.append(np.nan)
        ax1.errorbar(bin_c, p_m, yerr=p_s, fmt="ro-", lw=2, label="Mean Profile")
        ax1.legend(loc="upper right")

        # 2. dt vs Qmax
        ax2 = axes[0, 1]
        h2 = ax2.hist2d(sf_qmaxs, sf_dts, bins=[60, 80], range=[[-2, 12], [-5, 10]], cmap="Blues", cmin=1)
        ax2.set_xlabel("Peak Hit QDC", fontsize=12)
        ax2.set_ylabel(r"$t_{cluster} - t_0^{SF} - \mathrm{ToF}_\mu$ [ns]", fontsize=12)
        ax2.set_title("Timewalk Test: Cluster Time vs Peak Hit QDC", fontsize=13, fontweight="bold")
        ax2.grid(True, linestyle="--", alpha=0.5)
        fig.colorbar(h2[3], ax=ax2, label="Counts")

        # 3. dt vs L (Speed of Light)
        ax3 = axes[1, 0]
        h3 = ax3.hist2d(sf_Ls, sf_dts, bins=[50, 80], range=[[0, 45], [-5, 10]], cmap="Purples", cmin=1)
        ax3.set_xlabel("Propagation Distance along Fiber $L_{prop}$ [cm]", fontsize=12)
        ax3.set_ylabel(r"$t_{cluster} - t_0^{SF} - \mathrm{ToF}_\mu$ [ns]", fontsize=12)
        ax3.set_title(r"Effective Speed of Light: $\Delta t$ vs $L_{prop}$ ($t_0^{SF}$)", fontsize=13, fontweight="bold")
        ax3.grid(True, linestyle="--", alpha=0.5)
        fig.colorbar(h3[3], ax=ax3, label="Counts")

        L_bins = np.linspace(5, 42, 15)
        L_centers = (L_bins[:-1] + L_bins[1:]) / 2.0
        L_means, L_sems = [], []
        for ll, lh in zip(L_bins[:-1], L_bins[1:]):
            m = (sf_Ls >= ll) & (sf_Ls < lh) & (sf_dts >= -5) & (sf_dts <= 10)
            if np.sum(m) > 10:
                L_means.append(np.mean(sf_dts[m]))
                L_sems.append(np.std(sf_dts[m]) / np.sqrt(np.sum(m)))
            else:
                L_means.append(np.nan)
                L_sems.append(np.nan)
        ax3.errorbar(L_centers, L_means, yerr=L_sems, fmt="mo-", lw=2, label="Mean Profile")

        valid_fit = ~np.isnan(L_means)
        if np.sum(valid_fit) > 3:
            poly = np.polyfit(L_centers[valid_fit], np.array(L_means)[valid_fit], 1, w=1.0/np.array(L_sems)[valid_fit])
            slope = poly[0]
            c_fiber = 1.0 / slope if slope > 0 else 0
            fit_line = np.polyval(poly, L_centers)
            ax3.plot(L_centers, fit_line, "k--", lw=2.5, label=f"Fit: c_fiber = {c_fiber:.2f} cm/ns")
        ax3.legend(loc="upper left")

        # 4. dt vs L with DS reference time
        valid_ds = np.array([x is not None for x in plot_data["dt_ds"]])
        ds_dts = np.array([x for x in plot_data["dt_ds"] if x is not None])
        ds_Ls = np.array(plot_data["L"])[valid_ds]

        ax4 = axes[1, 1]
        h4 = ax4.hist2d(ds_Ls, ds_dts, bins=[50, 80], range=[[0, 45], [-18, 5]], cmap="Greens", cmin=1)
        ax4.set_xlabel("Propagation Distance along Fiber $L_{prop}$ [cm]", fontsize=12)
        ax4.set_ylabel(r"$t_{cluster} - t_0^{DS} - \mathrm{ToF}_\mu$ [ns]", fontsize=12)
        ax4.set_title(r"Effective Speed of Light with $t_0^{DS}$", fontsize=13, fontweight="bold")
        ax4.grid(True, linestyle="--", alpha=0.5)
        fig.colorbar(h4[3], ax=ax4, label="Counts")

        plt.tight_layout()
        if plot_output is None:
            plot_output = output_path.replace(".root", ".png")
        fig.savefig(plot_output, dpi=150)
        plt.close(fig)
        print(f"[SUCCESS] Diagnostic plot saved to: {plot_output}")


def main():
    args = parse_args()
    run_analysis(
        run_nr=args.run_number,
        partition=args.partition,
        max_events=args.max_events,
        output_path=args.output,
        geo_file_override=args.geo,
        windows_json=args.windows_json,
        make_plot=args.plot,
        plot_output=args.plot_output
    )


if __name__ == "__main__":
    main()
