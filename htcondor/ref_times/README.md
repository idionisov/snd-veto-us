# HTCondor Partition-Level Reference Time Extraction

Extracts SciFi and DS reference times (`reft-SF` and `reft-DS`) across all 2022 runs (Category I & II, >3M entries, nonzero luminosity, `is_physics_collision == True`).

Each raw partition file (`sndsw_raw-XXXX.root`) is processed as an independent, single-core HTCondor job over **all entries** without an event limit (no 10M breakpoint).

## Architecture

- **Partition arguments generator**: `generate_args.py` creates:
  - `args_partitions_all.txt` (7,764 total jobs)
  - `args_partitions_catI.txt` (4,375 jobs)
  - `args_partitions_catII.txt` (3,389 jobs)
- **HTCondor Submit file**: `ref_times.sub`
  - Flavour: `longlunch`
  - CPU: 1 core
  - Memory: 4GB
  - Disk: 2GB
- **Worker**: `run_ref_times_worker.sh`
  - Runs in local Condor scratch directory
  - Executes `ref_times.py --worker -r <RUN> -P <PARTITION> --break 0`
  - Atomically saves to `/eos/user/i/idioniso/Timing/ref_times_parts/<cat>/run<RUN>/part_<PARTITION>.root`
  - Automatic skip if target file already exists (safe resumption)
- **Merger**: `merge_ref_times.py` / `merge_ref_times.sh`
  - Sums all `part_*.root` histograms for each run and saves to `/eos/user/i/idioniso/Timing/reference_times_2022.root` under `catI/run<RUN>/` and `catII/run<RUN>/`.

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

To test submission with a single run or a few jobs, you can pass arguments or custom args file:
```bash
head -n 5 args_partitions_catI.txt > test_args.txt
condor_submit ref_times.sub args_file=test_args.txt flavour=workday
```

### 2. Check Progress
```bash
./status_ref_times.sh
```

### 3. Merge Output
Once jobs complete:
```bash
./merge_ref_times.sh
```
Or for a specific category:
```bash
./merge_ref_times.sh -c catI
./merge_ref_times.sh -c catII
```
