# HTCondor SciFi Cluster vs Reference Time Difference Extraction (`cscint_scifi`)

Extracts $t_{\text{SiPM}} - t_0^{\text{SF}}$ and $t_{\text{SiPM}} - t_0^{\text{DS}}$ vs predicted coordinate ($x_{\text{pred}}$ for horizontal mats, $y_{\text{pred}}$ for vertical mats) to determine the effective speed of light in SciFi fibers ($c_{\text{fiber}}$).

Each raw partition file (`sndsw_raw-XXXX.root`) is processed as an independent single-core HTCondor job over all events in the partition.

## Selection & Extraction Cuts
- **Preselection (hooked before tracking)**: $1 \le n_{\text{VetoHits}} \le 3$ and $6 \le n_{\text{ScifiHits}} < 27$
- **Track selection**: Clean SciFi track (`track_type == 1`, $\chi^2/\text{ndf} < 5.0$, $|\text{slope}_{x,y}| < 0.1\text{ rad}$)
- **Clusters**: Adjacent SiPM hits within $|d_{\text{meas}}| \le 1.0\text{ mm}$ of the track crossing point
- **Timing**: $t_{\text{SiPM}} = \min_{i \in \text{cluster}} (t_i \times \text{TDC2ns})$ (leading-edge arrival time)
- **Histograms**: Populated at plane level, per mat (`_mat0..2`), per SiPM array (`_matX_sipmY`), and globally (`_sipm0..11`)

## Structure

```
htcondor/cscint_scifi/
├── args_run5408.txt       # Arguments for all 91 partitions of Run 5408 (0 to 90)
├── cscint_scifi.sub       # HTCondor job description file
├── run_scifi_worker.sh    # Worker script executing scripts/scifi_cluster_ref_diff.py
├── submit_run5408.sh      # Helper to submit all 91 partitions of Run 5408
├── merge_cscint_scifi.sh  # Script to hadd partitions into runs/run5408.root
├── ddfUtils -> ...        # Symlink to ddfUtils
├── sndswEnv.sh -> ...     # Symlink to sndswEnv.sh
├── log/                   # HTCondor event logs
├── out/                   # HTCondor stdout
└── err/                   # HTCondor stderr
```

## Submitting Run 5408 Jobs

From an lxplus node:

```bash
cd /afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/cscint_scifi

# Submit all 91 partitions with default flavour (workday):
./submit_run5408.sh

# Or submit with custom flavour (e.g. longlunch or workday):
./submit_run5408.sh workday
```

Individual outputs are written to:
`/eos/user/i/idioniso/Timing/cscint_scifi_parts/catII/run5408/part_<P>.root`

## Merging Histograms

Once jobs finish, merge all partition files into the unified run file:

```bash
cd /afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/cscint_scifi

# Merge run 5408 partitions:
./merge_cscint_scifi.sh -r 5408

# Or with force overwrite:
./merge_cscint_scifi.sh -r 5408 -f
```

The unified merged file will be saved at:
`/eos/user/i/idioniso/Timing/cscint_scifi/runs/run5408.root`
