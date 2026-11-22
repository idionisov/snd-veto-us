# HTCondor cscint_fit Workflow

Parallel execution of `scripts/fit_timewalk.py` across Category II runs (1 job per run) with HTCondor flavour `workday`.

## Components
- `cscint_fit.sub`: HTCondor submission file configured for 1 run per job, flavour `workday`, 4GB memory, AlmaLinux 9.
- `run_fit_worker.sh`: Worker script executing `fit_timewalk.py` in node scratch, saving:
  - Calibration JSON to `/eos/user/i/idioniso/Timing/timewalk/fits/run<RUN>_timing_calibration.json`
  - Fit ROOT file with canvases to `/eos/user/i/idioniso/Timing/timewalk/fits_root/run<RUN>.root`
- `args_catII.txt`: List of all 33 Category II runs.
- `submit_fit.sh`: Submission CLI wrapper.
- `status_fit.sh`: Status inspection script checking jobs and EOS files.

## Usage

### 1. Submit all 33 Category II runs
```bash
./submit_fit.sh
```

### 2. Force re-fit (overwrite existing fits)
```bash
./submit_fit.sh --force
```

### 3. Submit specific runs
```bash
./submit_fit.sh -r 5236,5241,5350,5389
```

### 4. Monitor
```bash
./status_fit.sh
```
