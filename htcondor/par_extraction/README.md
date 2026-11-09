# TimeWalk Parameter Extraction: 250-Node Distributed Execution (Run 5999)

Distributed HTCondor calibration pipeline for `run_TimeWalk.py` on the full $133.8\,\text{M}$ event dataset of Run 5999.

## Architecture

1. **Step 1 (Speed Constants)**:
   - Evaluates $c_{\mathrm{scint}}$ on $2 \times 10^6$ prompt events to produce `run005999_cscintvalues.json` and `raw_cscint_histograms.root`.
2. **Step 2 (250 Single-Core HTCondor Jobs)**:
   - Partitions all $133,787,375$ events across 250 jobs ($\approx 535,150$ events/job, listed in `args_run5999_250jobs.txt`).
   - Each worker runs single-threaded with `--fillOnly` to generate `raw_histograms_<start>.root` in `/eos/user/i/idioniso/Timing/run005999/parallel_parts/part_<id>/`.
3. **Step 3 (Merger)**:
   - Merges all 250 raw histogram files (along with `raw_cscint_histograms.root`) into `merged_raw_histograms.root` using `hadd -f`.
4. **Step 4 (Final Fits & Calibration)**:
   - Executes `run_TimeWalk.py --fitOnly` on `merged_raw_histograms.root` to produce:
     - `run005999_timing_calibration.json`
     - `timewalk_calibration.root`

## File Inventory

- `run_TimeWalk.sh`: Master orchestrator running Steps 1–4.
- `submit_pExtr.sh`: Submission wrapper for HTCondor (`par_extraction.sub`).
- `par_extraction.sub`: HTCondor submit description file (single CPU, 4GB RAM, AlmaLinux 9).
- `run_TimeWalk_worker.sh`: Worker script executed on each HTCondor worker node.
- `status_pExtr.sh`: Monitors completion percentage on EOS and HTCondor queue status.
- `merge_and_fit.sh`: Performs `hadd` merging across all 250 jobs and runs final `--fitOnly`.
- `sndswEnv.sh`: Unmodified environment setup for lxplus worker nodes.
- `args_run5999_250jobs.txt`: Event start and length mappings for jobs 0 through 249.

## Workflow Commands

### 1. Run Step 1 (Extract $c_{\mathrm{scint}}$ constants)
```bash
./submit_pExtr.sh --step1
```

### 2. Submit the 250 Workers to HTCondor
```bash
# Submit all 250 jobs:
./submit_pExtr.sh

# Or submit a small test batch (e.g. jobs 0 to 4):
./submit_pExtr.sh -j 0-4

# Dry-run check:
./submit_pExtr.sh --dry-run
```

### 3. Monitor Progress
```bash
./status_pExtr.sh
```

### 4. Merge and Fit Once Complete
```bash
./merge_and_fit.sh
```
