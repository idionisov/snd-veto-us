# HTCondor cscint_fit Workflow

Parallel execution of fitting scripts across Category II and Category III runs (1 job per run) with HTCondor flavour `workday`.

## Components
- `cscint_fit.sub`: HTCondor submit file (flavour `workday`, 4GB RAM, 1 job per run).
- `run_fit_worker.sh`: Executes in node scratch and saves:
  - JSON calibrations to `/eos/.../fits/`
  - Updated ROOT files with canvases to `/eos/.../fits_root/`
- Target lists:
  - `args_catII.txt`: 33 runs (2022)
  - `args_catIII_2023.txt`: 10 runs (6079 - 6667)
  - `args_catIII_2024.txt`: 10 runs (8638 - 9880)
  - `args_catIII_2025.txt`: 10 runs (11124 - 12217)
  - `args_catIII_2026.txt`: 10 runs (13085 - 13520)
  - `args_catIII_all.txt`: All 40 Category III runs

## Usage

### Submit by Year (Category III)
```bash
./submit_catIII_2023.sh
./submit_catIII_2024.sh
./submit_catIII_2025.sh
./submit_catIII_2026.sh

# Or all 40 Cat III runs at once:
./submit_catIII_all.sh
```

### Submit Category II (33 runs)
```bash
./submit_catII.sh
```

### Options
Add `--force` to overwrite existing fits:
```bash
./submit_catIII_2024.sh --force
```

Submit specific runs:
```bash
./submit_fit.sh -r 9094,9269
```

### Monitor Progress
```bash
./status_fit.sh
```
