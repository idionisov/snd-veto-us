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

### 1. Submit Category II (Recommended Initial Batch)
```bash
cd /afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/timewalk
./submit_catII.sh
```
This submits 635 jobs across all 33 qualifying Category II runs (max 20 partitions/run) with `workday` flavour.

### 2. Submit All Categories
```bash
./submit_all_max20.sh
```

### 3. Monitor Progress
```bash
./status_timewalk.sh
# Or inspect specific run:
./status_timewalk.sh 5119
```

### 4. Merge Output Files
Once jobs finish:
```bash
# Merge all runs and categories
./merge_timewalk.sh

# Or merge only Category II:
./merge_timewalk.sh -c catII
```
