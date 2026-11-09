# TimeWalk Parameter Drift Study (1 Job per Run)

HTCondor batch setup to study calibration parameter drift across 2022 physics runs. Each HTCondor job processes **one complete run** up to $5 \times 10^6$ events using the `workday` queue.

## Selection Criteria from `pp2022.csv`
- **Category I** ("Veto and partial US misalignment"): 89 runs with $> 3,000,000$ entries (`args_run_catI.txt`).
- **Category II** ("Misalignment corrected"): 33 runs with $> 3,000,000$ entries (`args_run_catII.txt`).
- **Event Limit:** $5,000,000$ events/run (with $1,000,000$ prompt events used for $c_{\mathrm{scint}}$).
- **Flavour:** `workday` (8 hours).

## File Inventory
- `par_drift.sub`: HTCondor submit description file (`queue run from $(args_file)`).
- `run_TimeWalk_drift_worker.sh`: Single-thread worker script running `run_TimeWalk.py` in scratch.
- `submit_pDrift_catI.sh`: Submits all 89 Category I runs.
- `submit_pDrift_catII.sh`: Submits all 33 Category II runs.
- `submit_pDrift.sh`: Unified submit wrapper with support for categories, run subsets, event overrides, `--dry-run`, and `--force`.
- `status_pDrift.sh`: Progress auditor checking completed runs on EOS and HTCondor queue status.
- `args_run_catI.txt`: List of the 89 Category I run numbers.
- `args_run_catII.txt`: List of the 33 Category II run numbers.
- `pp2022.csv`: Master metadata catalog for 2022 pp runs.
- `sndswEnv.sh`: Unmodified environment setup for worker nodes.

## Usage Commands

### 1. Dry-Run Verification
```bash
# Category I dry-run:
./submit_pDrift_catI.sh --dry-run

# Category II dry-run:
./submit_pDrift_catII.sh --dry-run
```

### 2. Submit Category I (89 Runs)
```bash
./submit_pDrift_catI.sh
```

### 3. Submit Category II (33 Runs)
```bash
./submit_pDrift_catII.sh
```

### 4. Submit a Run Subset or Test
```bash
# Single run test with 10,000 events:
./submit_pDrift.sh -r 4427 -n 10000 -f espresso

# Run range:
./submit_pDrift.sh -r 4427,4449,4488
```

### 5. Monitor Completion Status
```bash
./status_pDrift.sh
```
