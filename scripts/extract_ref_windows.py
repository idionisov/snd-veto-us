#!/usr/bin/env python3
"""
Automatically extract dynamic reference time windows for Downstream (DS) and SciFi (SF) detectors.
Finds the dominant peak in reference time distributions, fits a local Gaussian to determine
precise mu, sigma, and [t_min, t_max] window boundaries per run.

Optionally exports output ROOT file(s) containing the original histograms, fitted functions,
and TCanvas displays with the accepted window shaded on top.
"""

import argparse
import glob
import json
import os
import re
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from scipy.optimize import curve_fit
import uproot


def gaus(t, a, mu, sig):
    return a * np.exp(-0.5 * ((t - mu) / sig) ** 2)


def fit_peak(edges, values, n_sigma=3.5, fit_half_width=1.5):
    """Locate the global maximum and fit a local Gaussian around it."""
    total_entries = float(np.sum(values))
    if total_entries < 50:
        return None

    x = 0.5 * (edges[:-1] + edges[1:])
    imax = int(np.argmax(values))
    x0 = float(x[imax])
    max_val = float(values[imax])

    mask = (x >= x0 - fit_half_width) & (x <= x0 + fit_half_width)
    if np.count_nonzero(mask) < 4:
        return None

    try:
        popt, _ = curve_fit(
            gaus,
            x[mask],
            values[mask],
            p0=[max_val, x0, 0.35],
            bounds=([0, x0 - fit_half_width, 0.05], [np.inf, x0 + fit_half_width, 2.0]),
            maxfev=2000,
        )
        mu = float(popt[1])
        sig = float(abs(popt[2]))
        t_min = float(round(mu - n_sigma * sig, 4))
        t_max = float(round(mu + n_sigma * sig, 4))
        return {
            "mu": round(mu, 4),
            "sigma": round(sig, 4),
            "t_min": t_min,
            "t_max": t_max,
            "peak_counts": int(max_val),
            "total_entries": int(total_entries),
        }
    except Exception:
        # Fallback to simple peak center +/- window if fit fails
        return {
            "mu": round(x0, 4),
            "sigma": 0.35,
            "t_min": round(x0 - n_sigma * 0.35, 4),
            "t_max": round(x0 + n_sigma * 0.35, 4),
            "peak_counts": int(max_val),
            "total_entries": int(total_entries),
        }


def create_fitted_canvas(hist, mu, sig, t_min, t_max, det_name="DS"):
    import ROOT

    c = ROOT.TCanvas(f"c_reft_{det_name}", f"{hist.GetTitle()} with Window", 900, 600)
    c.SetGrid()
    c.SetLeftMargin(0.12)
    c.SetRightMargin(0.08)
    c.SetTopMargin(0.08)
    c.SetBottomMargin(0.12)

    hist.GetXaxis().SetRangeUser(
        max(hist.GetXaxis().GetXmin(), mu - 15.0),
        min(hist.GetXaxis().GetXmax(), mu + 15.0),
    )
    hist.SetLineColor(ROOT.kBlack)
    hist.SetLineWidth(1)
    hist.Draw("HIST")

    ymax = hist.GetMaximum()
    hist.SetMaximum(ymax * 1.18)

    # Shaded accepted window
    box = ROOT.TBox(t_min, 0, t_max, ymax * 1.05)
    box.SetFillColorAlpha(ROOT.kAzure - 9, 0.40)
    box.SetLineColor(ROOT.kBlue + 2)
    box.SetLineStyle(2)
    box.SetLineWidth(2)
    box.Draw("SAME")

    hist.Draw("HIST SAME")

    # Fit function curve
    fit_func = ROOT.TF1(f"fit_{det_name}", "gaus", mu - 1.5, mu + 1.5)
    bin_idx = hist.FindBin(mu)
    fit_func.SetParameters(hist.GetBinContent(bin_idx), mu, sig)
    fit_func.SetLineColor(ROOT.kRed + 1)
    fit_func.SetLineWidth(2)
    fit_func.Draw("SAME")

    # Boundary lines
    l1 = ROOT.TLine(t_min, 0, t_min, ymax * 1.05)
    l1.SetLineColor(ROOT.kBlue + 2)
    l1.SetLineStyle(2)
    l1.SetLineWidth(2)
    l1.Draw("SAME")

    l2 = ROOT.TLine(t_max, 0, t_max, ymax * 1.05)
    l2.SetLineColor(ROOT.kBlue + 2)
    l2.SetLineStyle(2)
    l2.SetLineWidth(2)
    l2.Draw("SAME")

    # Legend
    leg = ROOT.TLegend(0.58, 0.65, 0.89, 0.89)
    leg.SetBorderSize(1)
    leg.SetFillColorAlpha(ROOT.kWhite, 0.85)
    leg.AddEntry(hist, f"{det_name} Reference Time", "l")
    leg.AddEntry(fit_func, f"Fit: #mu={mu:.2f} ns, #sigma={sig:.2f} ns", "l")
    leg.AddEntry(box, f"Window: [{t_min:.2f}, {t_max:.2f}] ns", "f")
    leg.Draw("SAME")

    c._keep = [box, fit_func, l1, l2, leg]
    return c, fit_func


def process_single_run(fpath, output_root_target=None, n_sigma=3.5):
    """Process a single ROOT file, fitting peaks and optionally writing a fitted ROOT file."""
    m = re.search(r"run(\d+)\.root", os.path.basename(fpath))
    run_nr = int(m.group(1)) if m else None

    out_record = {"run_nr": run_nr, "file": fpath}

    fit_results = {}
    try:
        with uproot.open(fpath) as tf:
            for det, hist_key in [("ds", "reft-DS"), ("sf", "reft-SF")]:
                if hist_key in tf:
                    v, edges = tf[hist_key].to_numpy()
                    res = fit_peak(edges, v, n_sigma=n_sigma)
                    if res:
                        for k, val in res.items():
                            out_record[f"{det}_{k}"] = val
                        fit_results[det] = res
                    else:
                        out_record[f"{det}_t_min"] = None
                        out_record[f"{det}_t_max"] = None
                else:
                    out_record[f"{det}_t_min"] = None
                    out_record[f"{det}_t_max"] = None

            if "ds" in fit_results and "sf" in fit_results:
                out_record["delta_t"] = round(fit_results["ds"]["mu"] - fit_results["sf"]["mu"], 4)
                out_record["delta_t_sigma"] = round(float(np.sqrt(fit_results["ds"]["sigma"]**2 + fit_results["sf"]["sigma"]**2)), 4)
    except Exception as e:
        out_record["error"] = str(e)

    # Optional ROOT output creation
    if output_root_target:
        try:
            import ROOT

            ROOT.gROOT.SetBatch(True)
            ROOT.gErrorIgnoreLevel = ROOT.kWarning

            os.makedirs(os.path.dirname(os.path.abspath(output_root_target)), exist_ok=True)
            in_file = ROOT.TFile.Open(fpath, "READ")
            if in_file and not in_file.IsZombie():
                # Write to temp file first to prevent corruption if interrupted
                tmp_out = f"{output_root_target}.tmp.{os.getpid()}"
                out_file = ROOT.TFile.Open(tmp_out, "RECREATE")

                for det, key_name in [("ds", "reft-DS"), ("sf", "reft-SF")]:
                    h = in_file.Get(key_name)
                    if h:
                        h_clone = h.Clone(key_name)
                        if det in fit_results:
                            res = fit_results[det]
                            c, fit_fn = create_fitted_canvas(
                                h_clone,
                                res["mu"],
                                res["sigma"],
                                res["t_min"],
                                res["t_max"],
                                det_name=det.upper(),
                            )
                            # Attach fit function to histogram
                            h_clone.GetListOfFunctions().Add(fit_fn)
                            out_file.cd()
                            h_clone.Write(key_name)
                            c.Write()
                        else:
                            out_file.cd()
                            h_clone.Write(key_name)

                # Copy any other existing keys
                for k in in_file.GetListOfKeys():
                    name = k.GetName()
                    if name not in ["reft-DS", "reft-SF"]:
                        obj = in_file.Get(name)
                        out_file.cd()
                        obj.Write(name)

                out_file.Close()
                in_file.Close()
                os.replace(tmp_out, output_root_target)
                out_record["output_root"] = output_root_target
        except Exception as e:
            out_record["root_error"] = str(e)

    return out_record


def worker_task(args_tuple):
    fpath, out_target, n_sigma = args_tuple
    return process_single_run(fpath, output_root_target=out_target, n_sigma=n_sigma)


def main():
    parser = argparse.ArgumentParser(
        description="Extract reference time windows per run, with optional fitted ROOT output."
    )
    parser.add_argument(
        "--input",
        "-i",
        default="/eos/user/i/idioniso/Timing/ref_times/runs",
        help="Input ROOT file or directory containing run*.root files",
    )
    parser.add_argument(
        "--output-root",
        "-o",
        default=None,
        help="Optional output ROOT file (if processing a single run) or output directory for fitted ROOT files",
    )
    parser.add_argument(
        "--output-csv",
        "-c",
        default="config/ref_time_windows.csv",
        help="Path for output CSV file",
    )
    parser.add_argument(
        "--output-json",
        "-j",
        default="config/ref_time_windows.json",
        help="Path for output JSON file",
    )
    parser.add_argument(
        "--n-sigma",
        "-s",
        type=float,
        default=3.5,
        help="Window width in number of sigmas (default: 3.5)",
    )
    parser.add_argument(
        "--n-workers",
        "-w",
        type=int,
        default=8,
        help="Number of parallel worker processes (default: 8)",
    )
    parser.add_argument(
        "--run",
        "-r",
        type=int,
        default=None,
        help="Filter for a specific run number",
    )
    args = parser.parse_args()

    # Determine list of input files
    if os.path.isfile(args.input):
        files = [args.input]
    elif os.path.isdir(args.input):
        pattern = os.path.join(args.input, "run*.root")
        files = sorted(glob.glob(pattern))
    else:
        # Check if glob pattern was given directly
        files = sorted(glob.glob(args.input))

    if args.run is not None:
        files = [f for f in files if f"run{args.run}.root" in os.path.basename(f)]

    if not files:
        raise FileNotFoundError(f"No run ROOT files found matching: {args.input}")

    # Determine output ROOT targets
    task_args = []
    for f in files:
        out_target = None
        if args.output_root:
            if len(files) == 1 and args.output_root.endswith(".root"):
                out_target = args.output_root
            else:
                out_target = os.path.join(args.output_root, os.path.basename(f))
        task_args.append((f, out_target, args.n_sigma))

    print(f"[INFO] Processing {len(files)} run file(s) with {args.n_workers} workers (n_sigma={args.n_sigma})...")
    if args.output_root:
        print(f"[INFO] ROOT files with fits and canvases will be written to: {args.output_root}")

    if args.n_workers > 1 and len(task_args) > 1:
        with ProcessPoolExecutor(max_workers=args.n_workers) as executor:
            records = list(executor.map(worker_task, task_args))
    else:
        records = [worker_task(t) for t in task_args]

    records = [r for r in records if r is not None]
    records.sort(key=lambda x: x["run_nr"] if x.get("run_nr") is not None else 0)

    # Save CSV
    if args.output_csv:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)), exist_ok=True)
        import pandas as pd

        df = pd.DataFrame(records)
        df.to_csv(args.output_csv, index=False)
        print(f"[INFO] Saved CSV windows to {args.output_csv}")

    # Save JSON
    if args.output_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)
        json_dict = {str(r["run_nr"]): r for r in records if r.get("run_nr") is not None}
        with open(args.output_json, "w") as jf:
            json.dump(json_dict, jf, indent=2)
        print(f"[INFO] Saved JSON windows to {args.output_json}")

    print(f"[INFO] Completed successfully for {len(records)} runs.")


if __name__ == "__main__":
    main()
