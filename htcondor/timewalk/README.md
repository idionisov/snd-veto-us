# HTCondor Time-Walk Extraction Pipeline

Automated extraction of Time-of-Flight (propagation speed) corrected Time-Walk 2D distributions ($dt$ vs QDC) across all qualifying runs and partitions.

## Output Structure

- **Partitions:** `/eos/user/i/idioniso/Timing/timewalk_parts/<category>/run<RUN>/part_<PARTITION>.root`
  - Each partition contains channel subdirectories `<detID_SiPM>/`:
    - `dtvqdc-DS` (ToF-corrected $t_0^{\text{DS}} - t_{\text{SiPM}}^{\text{ToF}}$ vs QDC)
    - `dtvqdc-SF` (ToF-corrected $t_0^{\text{SF}} - t_{\text{SiPM}}^{\text{ToF}}$ vs QDC)
    - `dtvqdc-DS-unified` (Unified $c_{\text{scint}}$ ToF-corrected $dt$ vs QDC)
    - `dtvqdc-SF-unified` (Unified $c_{\text{scint}}$ ToF-corrected $dt$ vs QDC)
- **Merged Runs:** `/eos/user/i/idioniso/Timing/timewalk/runs/run<RUN>.root`
- **Merged Categories:** `/eos/user/i/idioniso/Timing/timewalk/categories/<category>.root`

## Propagation Speed ($c_{\text{scint}}$) Constants

Constants are automatically resolved per run from:
`/eos/user/i/idioniso/Timing/cscint/fits/run<RUN>_cscint.json`
If not available, falls back to summary weighted mean, then placeholder speed (13.5 cm/ns).

## Submission Instructions (on lxplus)

### 1. Submit Category II
```bash
cd /afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/timewalk
./submit_catII.sh
```
This submits 635 jobs across all 33 qualifying Category II runs (max 20 partitions/run) with `workday` flavour.

### 2. Submit Category III (2023–2026 Runs)
```bash
# Submit all 40 Category III runs (800 jobs)
./submit_catIII.sh

# Or submit by specific year (200 jobs each):
./submit_catIII.sh 2023
./submit_catIII.sh 2024
./submit_catIII.sh 2025
./submit_catIII.sh 2026
```

### 3. Submit All Categories
```bash
./submit_all_max20.sh
```

### 4. Monitor Progress
```bash
./status_timewalk.sh
# Or inspect specific run:
./status_timewalk.sh 6079
```

### 5. Merge Output Files
Once jobs finish:
```bash
# Merge all runs and categories
./merge_timewalk.sh

# Or merge only Category III:
./merge_timewalk.sh -c catIII
```

---

# HTCondor Time-Walk Parameter Fitting Pipeline

Automated parallel fitting of merged 2D run distributions to extract rational time-walk parameters, channel-to-channel alignments $d_{\text{SiPM}}$, and embed $c_{\text{scint}}$ constants.

- **Submit script:** `submit_fits.sh`
- **Submit definition:** `fit_timewalk.sub`
- **Worker script:** `run_fit_worker.sh`
- **Status script:** `status_fits.sh`
- **Inputs:** `/eos/user/i/idioniso/Timing/timewalk/runs/run<RUN>.root`
- **Outputs:** `/eos/user/i/idioniso/Timing/timewalk/fits/run<RUN>_timing_calibration.json`

### Usage

```bash
cd /afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/timewalk

# Check status of fitted runs
./status_fits.sh

# Dry-run check for submission
./submit_fits.sh --dry-run

# Submit all uncompleted runs (microcentury flavour, ~1-2 min per run)
./submit_fits.sh

# Force re-fit of all runs
./submit_fits.sh --force

# Submit specific run(s)
./submit_fits.sh -r 5152,5247
```

