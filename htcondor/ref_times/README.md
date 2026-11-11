# HTCondor Partition-Level Reference Time Extraction

Extracts SciFi and DS reference times (`reft-SF` and `reft-DS`) across collision physics runs:
- **Category I & II (2022)**: All runs with >3M entries, nonzero luminosity, `is_physics_collision == True`.
- **Category III (2023–2026)**: The 10 runs with the most entries of each year, nonzero luminosity, `is_physics_collision == True`.

Each raw partition file (`sndsw_raw-XXXX.root`) is processed as an independent, single-core HTCondor job over **all entries** without an event limit (no 10M breakpoint).

## Selected Category III Runs (Top 10 by Entries per Year)

| Year | Threshold $X$ | Qualifying Runs (Run Number [Entries, Delivered Lumi]) | Total Partitions |
|---|---|---|---|
| **2023** | $> 227,000,000$ | **6640** (369.4M, 992.0 pb⁻¹), **6667** (331.9M, 802.8 pb⁻¹), **6590** (313.3M, 851.3 pb⁻¹), **6593** (298.1M, 804.1 pb⁻¹), **6596** (286.2M, 775.8 pb⁻¹), **6577** (286.1M, 779.3 pb⁻¹), **6663** (274.0M, 748.0 pb⁻¹), **6568** (268.4M, 728.4 pb⁻¹), **6574** (253.2M, 687.6 pb⁻¹), **6079** (227.8M, 826.7 pb⁻¹) | 2,914 |
| **2024** | $> 535,900,000$ | **9622** (703.8M, 1231.7 pb⁻¹), **9436** (613.8M, 907.2 pb⁻¹), **8638** (604.7M, 1084.7 pb⁻¹), **9685** (547.7M, 977.2 pb⁻¹), **9269** (546.8M, 953.9 pb⁻¹), **9094** (543.9M, 964.7 pb⁻¹), **9649** (542.8M, 963.2 pb⁻¹), **8724** (542.6M, 926.0 pb⁻¹), **9361** (537.7M, 942.4 pb⁻¹), **9880** (536.0M, 881.1 pb⁻¹) | 5,722 |
| **2025** | $> 361,000,000$ | **11193** (493.6M, 1392.1 pb⁻¹), **11720** (430.9M, 1230.2 pb⁻¹), **11241** (407.5M, 1158.6 pb⁻¹), **11747** (405.8M, 1188.8 pb⁻¹), **11555** (385.7M, 1069.0 pb⁻¹), **12205** (382.9M, 1101.0 pb⁻¹), **12213** (381.3M, 1099.6 pb⁻¹), **11124** (367.0M, 1046.5 pb⁻¹), **12217** (366.2M, 1052.5 pb⁻¹), **11744** (361.1M, 1066.4 pb⁻¹) | 3,987 |
| **2026** | $> 357,000,000$ | **13520** (515.8M, 1453.7 pb⁻¹), **13503** (407.5M, 1112.5 pb⁻¹), **13162** (398.0M, 1134.7 pb⁻¹), **13480** (395.5M, 1182.0 pb⁻¹), **13104** (385.8M, 1126.0 pb⁻¹), **13101** (372.2M, 1082.5 pb⁻¹), **13085** (366.0M, 1067.6 pb⁻¹), **13406** (365.2M, 1085.4 pb⁻¹), **13508** (361.4M, 1077.2 pb⁻¹), **13098** (357.2M, 1042.9 pb⁻¹) | 3,931 |

## Architecture

- **Partition arguments generator**: `generate_args.py` creates:
  - `args_partitions_all.txt` (24,318 total jobs)
  - `args_partitions_catI.txt` (4,375 jobs)
  - `args_partitions_catII.txt` (3,389 jobs)
  - `args_partitions_catIII.txt` (16,554 jobs)
  - `args_partitions_catIII_2023.txt` (2,914 jobs)
  - `args_partitions_catIII_2024.txt` (5,722 jobs)
  - `args_partitions_catIII_2025.txt` (3,987 jobs)
  - `args_partitions_catIII_2026.txt` (3,931 jobs)
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
  - Step 1: Merges partition histograms into run-level files `/eos/user/i/idioniso/Timing/ref_times/runs/run<RUN>.root`
  - Step 2: Merges run files into unified category files `/eos/user/i/idioniso/Timing/ref_times/categories/<category>.root` (`catI.root`, `catII.root`, `catIII.root`).

## Usage

### 1. Submit Jobs
Submit all jobs (24,318):
```bash
./submit_all.sh
```

#### Top 10 Runs (15 Partitions/Run = 600 Jobs Total):
Submit all 600 jobs across 2023–2026 (150 jobs/year):
```bash
./submit_catIII_max15.sh           # Submits 4 clusters of 150 jobs (one per year)
# or in a single cluster:
./submit_catIII_max15.sh --single  # Submits all 600 jobs in 1 cluster
```
Or submit individual years (150 jobs each):
```bash
./submit_catIII_max15.sh 2023      # 150 jobs
./submit_catIII_max15.sh 2024      # 150 jobs
./submit_catIII_max15.sh 2025      # 150 jobs
./submit_catIII_max15.sh 2026      # 150 jobs
```

#### Full Run Submissions:
By category:
```bash
./submit_catI.sh        # 4,375 jobs (2022)
./submit_catII.sh       # 3,389 jobs (2022)
./submit_catIII.sh      # 16,554 jobs (2023 - 2026)
```

Or Category III by year:
```bash
./submit_catIII_2023.sh # 2,914 jobs
./submit_catIII_2024.sh # 5,722 jobs
./submit_catIII_2025.sh # 3,987 jobs
./submit_catIII_2026.sh # 3,931 jobs
```

### 2. Check Progress
Full scan:
```bash
./status_ref_times.sh
```
Or for the 15-partition submission:
```bash
./status_ref_times.sh --max15
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
./merge_ref_times.sh -c catIII
```
