# HTCondor Partition-Level SiPM vs Reference Time Difference Extraction (`cscint`)

Extracts $t_0^{\text{DS}} - t_{\text{SiPM}}$ (`dt-DS`) and $t_0^{\text{SF}} - t_{\text{SiPM}}$ (`dt-SF`) for all 16 SiPMs on crossed Upstream (US) and Veto bars across all 2022 runs (Category I & II, >3M entries, nonzero luminosity, `is_physics_collision == True`).

Each raw partition file (`sndsw_raw-XXXX.root`) is processed as an independent, single-core HTCondor job over **all entries** without an event limit.

## Reference Time Windows (Updated)

In `scripts/sipm_ref_diff.py` and `TimeWalk.py`:
- **Category I**:
  - Region 1 ($run \le 4819$): $[14.0, 17.5]\text{ ns}$
  - Region 2 ($4820 \le run \le 5116$): $[16.5, 20.0]\text{ ns}$
  - Region 3 ($5175 \le run \le 5192$): $[5.5, 9.0]\text{ ns}$
- **Category II** ($5117 \le run \le 5174$ or $5193 \le run \le 5412$):
  - $[11.0, 16.0]\text{ ns}$

## Submitting Jobs (Max 15 Partitions Per Run)

To submit with a cap of 15 partitions per run:

```bash
cd htcondor/cscint

# 1. Generate argument lists capped at 15 partitions per run (fast mode)
./generate_args.py -p 15 --from-existing

# 2. Submit jobs:
./submit_top15p.sh catI    # Submits Category I (1,165 jobs)
./submit_top15p.sh catII   # Submits Category II (482 jobs)
./submit_top15p.sh all     # Submits All 2022 (1,647 jobs)
```

## Monitoring Progress

```bash
./status_cscint.sh
```

## Merging Histograms

Once jobs finish, run `merge_cscint.sh`:
- Merges all partition ROOT files into a single unified ROOT file per run:
  `/eos/user/i/idioniso/Timing/cscint/runs/run<RUN>.root`
- Merges all run files into a single unified ROOT file per category:
  `/eos/user/i/idioniso/Timing/cscint/categories/<catI|catII>.root`

```bash
# Merge all runs and categories
./merge_cscint.sh

# Or merge with 16 parallel hadd processes
./merge_cscint.sh -j 16

# Force re-merge
./merge_cscint.sh -f
```

## Submitting Category III Jobs (2023 - 2026, Top 10 Runs, Max 15 Partitions/Run)

```bash
cd htcondor/cscint

# Submit all 4 years (600 jobs in 4 clusters of 150)
./submit_top10_15p.sh

# Or submit a specific year only (150 jobs):
./submit_top10_15p.sh 2023
./submit_top10_15p.sh 2024
./submit_top10_15p.sh 2025
./submit_top10_15p.sh 2026

# Or submit all 600 jobs in a single cluster:
./submit_top10_15p.sh --single
```
