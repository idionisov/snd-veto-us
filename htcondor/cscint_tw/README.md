# Time-Walk Corrected $c_{\text{scint}}$ Extraction HTCondor Pipeline

This directory contains the complete HTCondor workflow to re-extract $c_{\text{scint}}$ (light propagation speed in scintillation bars) using hit signals corrected for Time-Walk delays:

$$\Delta t^{\text{TW}} = (t_0 - t_{\text{SiPM}}) - \left( \frac{\alpha}{\beta Q - Q_0} + \gamma Q \right)$$

where calibration parameters are loaded per-channel from:
`/eos/user/i/idioniso/Timing/timewalk/fits/run<RUN>_timing_calibration.json`

---

## Architecture Overview

```
Raw Partitions (EOS)
       │
       ▼ [1. Partition Extraction via cscint_tw.sub]
/eos/user/i/idioniso/Timing/cscint_tw_parts/<category>/run<RUN>/part_<PART>.root
       │
       ▼ [2. Run Merging via merge_runs.sub]
/eos/user/i/idioniso/Timing/cscint_tw/runs/run<RUN>.root
       │
       ▼ [3. c_scint Fitting via htcondor/cscint_fit]
/eos/user/i/idioniso/Timing/cscint_tw/fits/run<RUN>_cscint.json
```

---

## 1. Submitting Partition Jobs (Max 50 Partitions / Run)

Submit by category or data-taking year:

```bash
# Recommended: Start with Category II (33 runs, 1,478 partition jobs)
./submit_catII_max50.sh

# Category III by year:
./submit_catIII_2023_max50.sh   # 10 runs, 500 jobs
./submit_catIII_2025_max50.sh   # 10 runs, 500 jobs
./submit_catIII_2026_max50.sh   # 10 runs, 500 jobs

# All Category III (2023, 2025, 2026):
./submit_all_max50.sh catIII

# Everything (Cat II + Cat III):
./submit_all_max50.sh all
```

Monitor running jobs and output files on EOS:
```bash
./status_cscint_tw.sh
```

---

## 2. Merging Partitions into Run ROOT Files

Once partition jobs complete for a category or run:

```bash
# Merge Category II runs (33 runs)
./submit_merge_runs.sh catII

# Merge Category III runs
./submit_merge_runs.sh 2023
./submit_merge_runs.sh 2025
./submit_merge_runs.sh 2026

# Merge all runs
./submit_merge_runs.sh all

# Or merge a specific single run
./submit_merge_runs.sh -r 5119
```

Monitor run merging progress:
```bash
./status_merge_runs.sh
```

---

## 3. Re-Extracting $c_{\text{scint}}$ Fits

Once run ROOT files are merged in `/eos/user/i/idioniso/Timing/cscint_tw/runs/`, fit the speeds using `scripts/fit_cscint.py`:

```bash
python3 scripts/fit_cscint.py \
    -i /eos/user/i/idioniso/Timing/cscint_tw/runs/run5119.root \
    -o /eos/user/i/idioniso/Timing/cscint_tw/fits/run5119_cscint.json \
    --root-out /eos/user/i/idioniso/Timing/cscint_tw/fits_root/run5119.root
```
