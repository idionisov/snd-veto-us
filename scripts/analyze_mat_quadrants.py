#!/usr/bin/env python3
"""
analyze_mat_quadrants.py
------------------------
Computes SciFi and DS reference times and (t_ref - t_SiPM) across the 3x3
quadrants formed by SciFi Vertical Mats (measuring x) and Horizontal Mats (measuring y),
using the exact selection and time windows as in scripts/mufilter_cscint.py.

Generates:
1. mat_quadrants_run4968_1d_t0_sf.png: 3x3 grid of 1D counts for t_0^{SF} with window bounds
2. mat_quadrants_run4968_1d_t0_ds.png: 3x3 grid of 1D counts for t_0^{DS} with window bounds
3. mat_quadrants_run4968_1d_dt_sf.png: 3x3 grid of 1D counts for (t_0^{SF} - t_SiPM)
4. mat_quadrants_run4968_1d_dt_ds.png: 3x3 grid of 1D counts for (t_0^{DS} - t_SiPM)
5. mat_quadrants_run4968_4histograms_2d.png: 4-panel 3x3 2D summary heatmaps
"""

import os
import sys
import json
import time
import argparse
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_REPO_ROOT = "/afs/cern.ch/work/i/idioniso/snd-veto-us"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import ROOT
ROOT.gROOT.SetBatch(True)
ROOT.PyConfig.IgnoreCommandLineOptions = True

import SndlhcTracking
import Monitor
import AnalysisFunctions as af
import ddfUtils.mpl_styling as dms


def get_mat_indices(x, y):
    # V mat (x): Mat 0 [-47.5, -34.5], Mat 1 [-34.5, -21.5], Mat 2 [-21.5, -8.5]
    if -47.5 <= x < -34.5:
        iv = 0
    elif -34.5 <= x < -21.5:
        iv = 1
    elif -21.5 <= x <= -8.5:
        iv = 2
    else:
        iv = -1

    # H mat (y): Mat 0 [14.8, 27.8], Mat 1 [27.8, 40.8], Mat 2 [40.8, 53.8]
    if 14.8 <= y < 27.8:
        ih = 0
    elif 27.8 <= y < 40.8:
        ih = 1
    elif 40.8 <= y <= 53.8:
        ih = 2
    else:
        ih = -1

    return iv, ih


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-r", "--run", type=int, default=4968)
    parser.add_argument("-n", "--n-events", type=int, default=200000)
    parser.add_argument("-f", "--fname", type=str, default="/tmp/run_004968/sndsw_raw-0000.root")
    parser.add_argument("-g", "--geofile", type=str, default="/tmp/geofile_sndlhc_TI18_V4_2022.root")
    parser.add_argument("-w", "--windows-json", type=str, default="/tmp/ref_time_windows_4968.json")
    parser.add_argument("--sipm-ch", type=int, default=6, help="SiPM channel number to use (default: 6)")
    parser.add_argument("-o", "--output-prefix", type=str, default="mat_quadrants_run4968")
    args = parser.parse_args()

    # Load time windows from json
    with open(args.windows_json, "r") as f:
        windows_dict = json.load(f)
    win = windows_dict.get(str(args.run), {})
    tsf0_min = float(win.get("sf_t_min", 2.3566))
    tsf0_max = float(win.get("sf_t_max", 4.2566))
    tds0_min = float(win.get("ds_t_min", 23.3516))
    tds0_max = float(win.get("ds_t_max", 25.5955))

    print(f"Time Windows for Run {args.run}:")
    print(f"  t0^SF: [{tsf0_min:.3f}, {tsf0_max:.3f}] ns")
    print(f"  t0^DS: [{tds0_min:.3f}, {tds0_max:.3f}] ns")

    geo_file_opt = "../" + os.path.abspath(args.geofile)

    options = type("Opts", (), {
        "runNumber": args.run,
        "numuStudy": False,
        "nueStudy": False,
        "state": "raw",
        "CorrectionType": "DS",
        "referencesystem": 3,
        "datalocation": "physics",
        "simulation": False,
        "geoFile": geo_file_opt,
        "path": "",
        "server": "",
        "online": False,
        "fname": args.fname,
        "partition": 0,
        "interactive": False,
        "saveTo": "/tmp",
        "nStart": 0,
        "nEvents": args.n_events,
        "trackType": "ScifiDS",
    })()

    analysis = af.Analysis(options)
    track_task = SndlhcTracking.Tracking()
    track_task.SetName("simpleTracking")

    M = Monitor.Monitoring(options, [track_task])
    M.M = M
    analysis.SetTask(M)

    # Geometry pre-fetch
    nav = ROOT.gGeoManager.GetCurrentNavigator()
    mu_filter = M.MuFilter
    tdc2ns = analysis.TDC2ns

    # Monkey-patch GetDSHaverage
    def safe_GetDSHaverage(self, hits, mode="tds0"):
        if mode == "tds0":
            stations = {i.GetDetectorID(): i for i in hits}
            total = {i: 0 for i in range(4)}
            counter = {i: 0 for i in range(4)}
            theTrack = getattr(self, "current_ds_track", None)
            if theTrack is None:
                if not hasattr(self.task.M, "Reco_MuonTracks") or self.task.M.Reco_MuonTracks.GetEntries() == 0:
                    return -999.0
                theTrack = self.task.M.Reco_MuonTracks[0]

            nM = theTrack.getNumPointsWithMeasurement()
            for n in range(nM):
                M_pt = theTrack.getPointWithMeasurement(n)
                W = M_pt.getRawMeasurement()
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

            if counter[1] > 0 and counter[2] > 0:
                return (total[1] / counter[1] + total[2] / counter[2]) / 2.0
            elif counter[1] > 0:
                return total[1] / counter[1]
            elif counter[2] > 0:
                return total[2] / counter[2]
            return -999.0
        return -999.0

    af.Analysis.GetDSHaverage = safe_GetDSHaverage

    # Upstream plane z positions for bar intersection
    us_z_planes = {}
    for plane in range(mu_filter.GetConfParI("MuFilter/NUpstreamPlanes")):
        detID = 20000 + plane * 1000
        A, B = ROOT.TVector3(), ROOT.TVector3()
        mu_filter.GetPosition(detID, A, B)
        us_z_planes[plane] = (A.z() + B.z()) / 2.0

    # Data stores for 3x3 quadrants: [ih][iv]
    # 1. Unconstrained reference times (to check full distribution against window)
    quad_tsf_raw = [[[] for _ in range(3)] for _ in range(3)]
    quad_tds_raw = [[[] for _ in range(3)] for _ in range(3)]

    # 2. Window-selected reference times (exact mufilter_cscint.py)
    quad_tsf_win = [[[] for _ in range(3)] for _ in range(3)]
    quad_tds_win = [[[] for _ in range(3)] for _ in range(3)]

    # 3. Differences t_ref - t_SiPM (exact mufilter_cscint.py)
    quad_dt_sf = [[[] for _ in range(3)] for _ in range(3)]
    quad_dt_ds = [[[] for _ in range(3)] for _ in range(3)]

    actual_entries = M.GetEntries()
    events_to_process = min(args.n_events, actual_entries) if args.n_events > 0 else actual_entries

    print(f" ~ Processing {events_to_process:,} events...", flush=True)
    t0 = time.time()

    for n in range(events_to_process):
        if n > 0 and n % 25000 == 0:
            elapsed = time.time() - t0
            print(f"   Event {n:,} / {events_to_process:,} ({n/elapsed:.1f} ev/s)", flush=True)

        event = M.GetEvent(n)

        # 1. Category I pre-selection: require Veto hit OR SciFi station 1 hit
        has_veto = any(h.isValid() and (h.GetDetectorID() // 10000 == 1) for h in event.Digi_MuFilterHits)
        has_scifi1 = any(h.isValid() and (h.GetStation() == 1 if hasattr(h, "GetStation") else h.GetDetectorID() // 1000000 == 1) for h in event.Digi_ScifiHits)
        if not (has_veto or has_scifi1):
            continue

        # 2. Track quality and classification (exact matching mufilter_cscint.py)
        qualified_ds_tracks = []
        qualified_sf_tracks = []
        for trk in M.Reco_MuonTracks:
            fit_status = trk.getFitStatus()
            if not fit_status.isFitConverged():
                continue
            chi2ndf = fit_status.getChi2() / fit_status.getNdf() if fit_status.getNdf() > 0 else 999.0
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

        # 3. Evaluate track position at SciFi center (z = 320 cm) to determine quadrant
        ref_track = best_sf if best_sf else best_ds
        pos_ref = ref_track["pos"]
        mom_ref = ref_track["mom"]
        tx = mom_ref.x() / mom_ref.z()
        ty = mom_ref.y() / mom_ref.z()
        x_track = pos_ref.x() + (320.0 - pos_ref.z()) * tx
        y_track = pos_ref.y() + (320.0 - pos_ref.z()) * ty

        iv, ih = get_mat_indices(x_track, y_track)
        if iv < 0 or ih < 0:
            continue

        # 4. Extract Reference Times (raw and window-checked)
        tsf0 = analysis.GetScifiAverageTime(M.Scifi, event.Digi_ScifiHits, mode="tsf0")
        has_valid_sf = False
        tsf0_val = None
        if isinstance(tsf0, (tuple, list)):
            if tsf0[0] != -999.:
                tsf0_val = tsf0[0]
        elif tsf0 != -999.:
            tsf0_val = tsf0

        if tsf0_val is not None:
            quad_tsf_raw[ih][iv].append(tsf0_val)
            if tsf0_min <= tsf0_val <= tsf0_max:
                has_valid_sf = True
                quad_tsf_win[ih][iv].append(tsf0_val)
            else:
                tsf0_val = None

        tds0 = analysis.GetDSHaverage(event.Digi_MuFilterHits, mode="tds0")
        has_valid_ds = False
        tds0_val = None
        if isinstance(tds0, (tuple, list)):
            if tds0[0] != -999.:
                tds0_val = tds0[0]
        elif tds0 != -999.:
            tds0_val = tds0

        if tds0_val is not None:
            quad_tds_raw[ih][iv].append(tds0_val)
            if tds0_min <= tds0_val <= tds0_max:
                has_valid_ds = True
                quad_tds_win[ih][iv].append(tds0_val)
            else:
                tds0_val = None

        if not has_valid_ds and not has_valid_sf:
            continue

        # 5. Predict crossed Upstream bars and extract t_sipm (exact as mufilter_cscint.py)
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
                            expected_us_bars[plane] = (bar_det_id, xEx)
                        except ValueError:
                            pass

        for hit in event.Digi_MuFilterHits:
            detID = hit.GetDetectorID()
            s = detID // 10000
            p = (detID % 10000) // 1000
            b = detID % 1000

            # Only Upstream bars
            if s != 2:
                continue
            if not best_ds or p not in expected_us_bars or expected_us_bars[p][0] != detID:
                continue

            channels_t = hit.GetAllTimes()
            signals_dict = dict(hit.GetAllSignals())

            for item in channels_t:
                sipm_num, clock = item
                if sipm_num < 0 or sipm_num > 15:
                    continue
                if analysis.IsSmallSiPMchannel(sipm_num):
                    continue
                if args.sipm_ch is not None and args.sipm_ch >= 0 and sipm_num != args.sipm_ch:
                    continue

                qdc = signals_dict.get(sipm_num, -999.)
                if qdc == -999. or qdc <= 0:
                    continue

                t_sipm = clock * tdc2ns

                if has_valid_sf and tsf0_val is not None:
                    dt_sf = tsf0_val - t_sipm
                    quad_dt_sf[ih][iv].append(dt_sf)

                if has_valid_ds and tds0_val is not None:
                    dt_ds = tds0_val - t_sipm
                    quad_dt_ds[ih][iv].append(dt_ds)

    elapsed = time.time() - t0
    print(f"\nProcessed {events_to_process:,} events in {elapsed:.2f}s ({events_to_process/elapsed:.0f} ev/s)!", flush=True)

    # ---------------- PLOTTING HELPER ----------------
    v_labels = ["V Mat 0\n[-47.5, -34.5]", "V Mat 1\n[-34.5, -21.5]", "V Mat 2\n[-21.5, -8.5]"]
    h_labels = ["H Mat 0\n[14.8, 27.8]", "H Mat 1\n[27.8, 40.8]", "H Mat 2\n[40.8, 53.8]"]

    def plot_3x3_1d(data_grid, title, xlabel, out_path, x_range, color, window_bounds=None, vlines_legend=None):
        fig, axes = plt.subplots(3, 3, figsize=(15, 12), sharex=True)
        for ih in [2, 1, 0]:
            ax_row = 2 - ih  # Top row is H Mat 2
            for iv in range(3):
                ax = axes[ax_row, iv]
                vals = data_grid[ih][iv]
                if len(vals) > 0:
                    n_tot = len(vals)
                    ax.hist(vals, bins=80, range=x_range, color=color, alpha=0.7, label=f"N={n_tot:,}")
                    mean_val = np.mean(vals)
                    std_val = np.std(vals)
                    ax.axvline(mean_val, color="darkorange", linestyle="-", linewidth=1.8, label=f"Mean={mean_val:.2f}±{std_val:.2f}")

                    # Draw window bounds if given
                    if window_bounds is not None:
                        w_min, w_max = window_bounds
                        n_in = np.sum((np.array(vals) >= w_min) & (np.array(vals) <= w_max))
                        in_frac = (n_in / n_tot) * 100.0 if n_tot > 0 else 0.0
                        ax.axvline(w_min, color="crimson", linestyle="--", linewidth=1.8, label=f"Window: [{w_min:.2f}, {w_max:.2f}]")
                        ax.axvline(w_max, color="crimson", linestyle="--", linewidth=1.8)
                        ax.axvspan(w_min, w_max, color="crimson", alpha=0.08)
                        # Add textbox with in-window efficiency
                        ax.text(0.04, 0.72, f"In Window: {in_frac:.1f}%\n({n_in:,}/{n_tot:,})",
                                transform=ax.transAxes, fontsize=10, fontweight="bold",
                                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.85, edgecolor="gray"))

                ax.set_title(f"H Mat {ih} × V Mat {iv}", fontsize=11, fontweight="bold")
                ax.grid(True, linestyle=":", alpha=0.5)
                ax.legend(fontsize=9, loc="upper right")
                if ax_row == 2:
                    ax.set_xlabel(xlabel, fontsize=11)
                if iv == 0:
                    ax.set_ylabel(f"H Mat {ih}\nCounts", fontsize=11)

        fig.suptitle(title, fontsize=15, fontweight="bold", y=0.995)
        plt.tight_layout()
        plt.savefig(out_path, dpi=180)
        plt.close()
        print(f"Saved 3x3 1D plot to: {out_path}")

    # 1. Plot 1D counts for t_0^{SF} with allowed window bounds
    out_1d_tsf = f"/afs/cern.ch/work/i/idioniso/snd-veto-us/{args.output_prefix}_1d_t0_sf.png"
    plot_3x3_1d(
        data_grid=quad_tsf_raw,
        title=r"Run 4968: SciFi Reference Time $t_0^{\mathrm{SF}}$ 1D Distributions across 3$\times$3 Mat Quadrants",
        xlabel=r"$t_0^{\mathrm{SF}}$ [ns]",
        out_path=out_1d_tsf,
        x_range=[-5, 15],
        color="royalblue",
        window_bounds=(tsf0_min, tsf0_max)
    )

    # 2. Plot 1D counts for t_0^{DS} with allowed window bounds
    out_1d_tds = f"/afs/cern.ch/work/i/idioniso/snd-veto-us/{args.output_prefix}_1d_t0_ds.png"
    plot_3x3_1d(
        data_grid=quad_tds_raw,
        title=r"Run 4968: DS Reference Time $t_0^{\mathrm{DS}}$ 1D Distributions across 3$\times$3 Mat Quadrants",
        xlabel=r"$t_0^{\mathrm{DS}}$ [ns]",
        out_path=out_1d_tds,
        x_range=[15, 35],
        color="forestgreen",
        window_bounds=(tds0_min, tds0_max)
    )

    # 3. Plot 1D counts for (t_0^{SF} - t_SiPM)
    out_1d_dt_sf = f"/afs/cern.ch/work/i/idioniso/snd-veto-us/{args.output_prefix}_1d_dt_sf.png"
    plot_3x3_1d(
        data_grid=quad_dt_sf,
        title=r"Run 4968: $t_0^{\mathrm{SF}} - t_{\mathrm{SiPM}}$ (SiPM 6) 1D Distributions across 3$\times$3 Quadrants",
        xlabel=r"$t_0^{\mathrm{SF}} - t_{\mathrm{SiPM}}$ [ns]",
        out_path=out_1d_dt_sf,
        x_range=[-20, 5],
        color="purple"
    )

    # 4. Plot 1D counts for (t_0^{DS} - t_SiPM)
    out_1d_dt_ds = f"/afs/cern.ch/work/i/idioniso/snd-veto-us/{args.output_prefix}_1d_dt_ds.png"
    plot_3x3_1d(
        data_grid=quad_dt_ds,
        title=r"Run 4968: $t_0^{\mathrm{DS}} - t_{\mathrm{SiPM}}$ (SiPM 6) 1D Distributions across 3$\times$3 Quadrants",
        xlabel=r"$t_0^{\mathrm{DS}} - t_{\mathrm{SiPM}}$ [ns]",
        out_path=out_1d_dt_ds,
        x_range=[0, 20],
        color="darkorange"
    )

    # 5. Update 2D 4-panel summary heatmap
    datasets_2d = [
        ("t_0^{SF} [ns]", quad_tsf_win, "Blues", r"$t_0^{\mathrm{SF}}$ (Window: [2.36, 4.26] ns)"),
        ("t_0^{DS} [ns]", quad_tds_win, "Greens", r"$t_0^{\mathrm{DS}}$ (Window: [23.35, 25.60] ns)"),
        (r"t_0^{SF} - t_{SiPM} [ns]", quad_dt_sf, "Purples", r"$t_0^{\mathrm{SF}} - t_{\mathrm{SiPM}}$ (SiPM 6)"),
        (r"t_0^{DS} - t_{SiPM} [ns]", quad_dt_ds, "Oranges", r"$t_0^{\mathrm{DS}} - t_{\mathrm{SiPM}}$ (SiPM 6)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(16, 14))
    for idx, (label, data_grid, cmap, title) in enumerate(datasets_2d):
        ax = axes[idx // 2, idx % 2]
        mean_mat = np.full((3, 3), np.nan)
        std_mat = np.full((3, 3), np.nan)
        cnt_mat = np.zeros((3, 3), dtype=int)

        for ih in range(3):
            for iv in range(3):
                vals = data_grid[ih][iv]
                if len(vals) > 0:
                    mean_mat[ih, iv] = np.mean(vals)
                    std_mat[ih, iv] = np.std(vals)
                    cnt_mat[ih, iv] = len(vals)

        im = ax.imshow(mean_mat, origin="lower", cmap=cmap, aspect="auto")
        ax.set_xticks(range(3))
        ax.set_xticklabels(v_labels, fontsize=11)
        ax.set_yticks(range(3))
        ax.set_yticklabels(h_labels, fontsize=11)
        ax.set_xlabel("SciFi Vertical Mat (measuring $x$) [cm]", fontsize=12)
        ax.set_ylabel("SciFi Horizontal Mat (measuring $y$) [cm]", fontsize=12)
        ax.set_title(f"{title}\nMean across 3×3 Quadrants", fontsize=13, fontweight="bold")
        fig.colorbar(im, ax=ax, label=label)

        for ih in range(3):
            for iv in range(3):
                m = mean_mat[ih, iv]
                s = std_mat[ih, iv]
                n = cnt_mat[ih, iv]
                if not np.isnan(m):
                    text = f"{m:.2f} ns\n± {s:.2f}\n(N={n:,})"
                else:
                    text = "N/A"
                ax.text(iv, ih, text, ha="center", va="center", color="black", fontweight="bold", fontsize=11)

    plt.suptitle(f"Run {args.run}: 3×3 Mat Quadrants Analysis (Exact mufilter_cscint.py Cuts)", fontsize=16, fontweight="bold", y=0.995)
    plt.tight_layout()
    out_2d_path = f"/afs/cern.ch/work/i/idioniso/snd-veto-us/{args.output_prefix}_4histograms_2d.png"
    plt.savefig(out_2d_path, dpi=180)
    plt.close()
    print(f"Saved 4 3x3 2D Histograms to: {out_2d_path}")

    # Summary table for console
    print("\n" + "="*75)
    print(" IN-WINDOW EFFICIENCY: t_0^{SF} [%] across 3x3 Quadrants")
    print("="*75)
    for ih in [2, 1, 0]:
        row_str = f"H Mat {ih} | "
        for iv in range(3):
            all_v = quad_tsf_raw[ih][iv]
            win_v = quad_tsf_win[ih][iv]
            eff = len(win_v) / len(all_v) * 100 if len(all_v) > 0 else 0
            row_str += f"V{iv}: {eff:.1f}% ({len(win_v):,}/{len(all_v):,}) | "
        print(row_str)

    print("\n" + "="*75)
    print(" IN-WINDOW EFFICIENCY: t_0^{DS} [%] across 3x3 Quadrants")
    print("="*75)
    for ih in [2, 1, 0]:
        row_str = f"H Mat {ih} | "
        for iv in range(3):
            all_v = quad_tds_raw[ih][iv]
            win_v = quad_tds_win[ih][iv]
            eff = len(win_v) / len(all_v) * 100 if len(all_v) > 0 else 0
            row_str += f"V{iv}: {eff:.1f}% ({len(win_v):,}/{len(all_v):,}) | "
        print(row_str)


if __name__ == "__main__":
    main()
