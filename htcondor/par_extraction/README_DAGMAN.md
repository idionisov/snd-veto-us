# End-to-End Automated Calibration with HTCondor DAGMan

This directory provides automated DAGMan workflows that chain **full-statistics $c_{\mathrm{scint}}$ speed extraction**, **time-walk histogram accumulation**, and **final profile fitting** without requiring manual intervention between stages.

---

## Architecture & Topology

Every run is processed through an automated 4-node DAG:

```
[STAGE 1: c_scint]
  STAGE1_SPEED (N parallel jobs)
  - Accumulates prompt hits into dtvxpred across all N event partitions
         │
         ▼
  MERGE_FIT_SPEED (1 intermediate merger node)
  - Merges all N raw c_scint histogram files via hadd
  - Fits linear slopes across all statistics using 5-segment 85%-overlap model
  - Exports: run<runNr>_cscintvalues.json
         │
         ▼
[STAGE 2: Time-Walk & Fine Alignment]
  STAGE2_TW (N parallel jobs)
  - Automatically loads the full-statistics run<runNr>_cscintvalues.json
  - Performs photon ToF corrections and fills dtvqdc
         │
         ▼
  MERGE_FIT_FINAL (1 final merger node)
  - Merges all N raw TimeWalk histogram files via hadd
  - Fits 5-parameter rational models and extracts channel-to-channel alignment
  - Exports: run<runNr>_timing_calibration.json & timewalk_calibration.root
```

---

## How to Submit a Pipeline for Any Arbitrary Run

### Step 1: Generate the Pipeline Files

Use the helper script `make_run_pipeline.py`. It partitions the run's events and creates the `.dag` and submit script automatically:

```bash
cd /afs/cern.ch/work/i/idioniso/snd-veto-us/htcondor/par_extraction

# For 2022 physics runs with known entries in pp2022.csv (auto-detects events):
python3 make_run_pipeline.py -r 5100

# For arbitrary runs (specifying total events explicitly):
python3 make_run_pipeline.py -r 6640 -n 120000000

# Customizing number of parallel jobs and HTCondor flavour (default: 250 jobs, workday):
python3 make_run_pipeline.py -r 5097 -j 250 -f workday
```

This generates three files:
1. `args_run<RUN>_<JOBS>jobs.txt` — Partition map with `[job_id start n_events]`.
2. `run<RUN>_pipeline.dag` — The complete DAGMan dependency definition.
3. `submit_dag_run<RUN>.sh` — Executable submit wrapper.

---

### Step 2: Submit to HTCondor (from lxplus)

```bash
./submit_dag_run<RUN>.sh
```

*(Or invoke directly: `condor_submit_dag run<RUN>_pipeline.dag`)*

---

## Quick-Start Examples for Pre-Configured Runs

### 1. Test Pipeline (Run 6640, 500,000 events, 1 job per stage):
```bash
./submit_dag_test_run6640.sh
```

### 2. Full-Statistics Production Run 5100 (131.8M events, 250 parallel jobs):
```bash
./submit_dag_run5100.sh
```

---

## Monitoring and Management

### Check DAG Status in the HTCondor Queue:
```bash
condor_q -dag
```

### Stream Live DAGMan Decision and Execution Logs:
```bash
tail -f run<RUN>_pipeline.dag.dagman.out
```

### Check Worker Node Output & Error Logs:
- Worker stdout: `out/tw_part<id>_<ClusterId>_<ProcId>.out`
- Worker stderr: `err/tw_part<id>_<ClusterId>_<ProcId>.err`
- Intermediate & Final Merge logs: `out/dag_merge_run<RUN>_*.out`

### Suspend or Cancel a Running Pipeline:
```bash
# To pause:
condor_hold <DAGMan_ClusterId>

# To kill all stages:
condor_rm <DAGMan_ClusterId>
```
