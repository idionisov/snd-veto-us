# HTCondor Partition-Level SiPM vs Reference Time Difference Extraction (`cscint`)

Extracts $t_0^{\text{DS}} - t_{\text{SiPM}}$ (`dt-DS`) and $t_0^{\text{SF}} - t_{\text{SiPM}}$ (`dt-SF`) for all 16 SiPMs on crossed Upstream (US) and Veto bars across all 2022 runs (Category I & II, >3M entries, nonzero luminosity, `is_physics_collision == True`).

Each raw partition file (`sndsw_raw-XXXX.root`) is processed as an independent, single-core HTCondor job over **all entries** without an event limit (no 10M breakpoint).

## Physics & Track Matching Logic

- **Upstream (US) Bars ($s=2$, detID `20000..24009`)**:
  - Always extrapolated and matched with **Downstream (DS)** tracks (`ttype == 3`).
- **Veto Bars ($s=1$, detID `10000..11006`)**:
  - Always extrapolated and matched with **SciFi** tracks (`ttype == 1`).
- **Track Selection Cuts**:
  - Reconstructed track with $\chi^2/\text{ndf} < 5.0$.
  - Slopes $|p_x/p_z| < 0.1$ and $|p_y/p_z| < 0.1$ in both projections.
- **Reference Time Cuts**:
  - $t_0^{\text{DS}}$ category-dependent windows:
    - **Category I** ($run \le 5116$ or $5175 \le run \le 5192$): $20.25 \le t_0^{\text{DS}} \le 24.15\text{ ns}$
    - **Category II** ($5117 \le run \le 5174$ or $5193 \le run \le 5412$): $13.0 \le t_0^{\text{DS}} \le 15.5\text{ ns}$
    - **Category III** (all others): $18.5 \le t_0^{\text{DS}} \le 20.5\text{ ns}$
  - No cut applied on SciFi reference time $t_0^{\text{SF}}$.
- **Output Hierarchy in ROOT**:
  - Subdirectories `XXXXX_Y/` where `XXXXX` is the 5-digit detector ID and `Y` is the SiPM index ($0..15$).
  - Histograms `dt-DS` and `dt-SF` inside each subdirectory.

## Architecture

- **Partition Arguments Generator**: `generate_args.py` creates:
  - `args_partitions_all.txt` (7,764 total jobs)
  - `args_partitions_catI.txt` (4,375 jobs)
  - `args_partitions_catII.txt` (3,389 jobs)
- **HTCondor Submit File**: `cscint.sub`
  - Flavour: `longlunch` (2 hours)
  - CPU: 1 core
  - Memory: 4GB
  - Disk: 2GB
- **Worker Script**: `run_cscint_worker.sh`
  - Runs in local Condor scratch directory
  - Executes `sipm_ref_diff.py --worker -r <RUN> -P <PARTITION> --break 0`
  - Atomically saves to `/eos/user/i/idioniso/Timing/cscint_parts/<cat>/run<RUN>/part_<PARTITION>.root`
  - Automatically skips completed partitions for safe resumption
- **Merger Script**: `merge_cscint.sh`
  - Merges all partition files of each run into a single run file: `/eos/user/i/idioniso/Timing/cscint/runs/run<RUN>.root`
  - Merges all run files into category ROOT files: `/eos/user/i/idioniso/Timing/cscint/categories/<category>.root`

## Usage

### 1. Submit Jobs
To submit all jobs:
```bash
./submit_all.sh
```

Or by category:
```bash
./submit_catI.sh   # 4,375 jobs
./submit_catII.sh  # 3,389 jobs
```

To run a test with a few jobs:
```bash
head -n 5 args_partitions_catI.txt > test_args.txt
condor_submit cscint.sub args_file=test_args.txt
```

### 2. Monitor Progress
```bash
./status_cscint.sh
```

### 3. Merge Output
Once jobs complete:
```bash
./merge_cscint.sh
```

Options:
```bash
./merge_cscint.sh -c catI        # Merge category I only
./merge_cscint.sh -c catII       # Merge category II only
./merge_cscint.sh -r 4427        # Merge only run 4427
./merge_cscint.sh -j 16          # Use 16 parallel hadd workers
./merge_cscint.sh -f             # Force re-merge even if output exists
```
