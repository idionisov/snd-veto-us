# SND@LHC Veto & Upstream MuFilter Timing Calibration: Adaptations and Improvements

This document details the complete sequence of adaptations, methodological refinements, and software modernizations implemented in the SND@LHC upstream muon timing calibration framework, comparing the current pipeline with the original work and codebase developed by Andrew Conaboy (PhD Dissertation, 2024; branch `aconaboy/master`).

---

## 1. Executive Summary & Architecture Comparison

| Feature / Step | Andrew Conaboy's Original Implementation | Our Modernized Implementation |
| :--- | :--- | :--- |
| **Pipeline Execution** | Disjoint multi-step workflow requiring separate script invocations, manual file handoffs, and intermediate steps. | Fully unified, mode-free execution: running `run_TimeWalk.py` runs Pass 1 ($c_{\text{scint}}$) $\to$ in-memory transfer $\to$ Pass 2 (ToF) $\to$ TW fit $\to$ consolidated outputs in a single command. |
| **Propagation Speed $c_{\text{scint}}$ Fit Range** | Unconstrained / hard-coded across entire bar length $[-80, +5]\text{ cm}$, susceptible to edge coupling distortions and tracking limits. | Physically constrained to $[-55.0, -5.0]\text{ cm}$, honoring Downstream tracking acceptance ($x > -58\text{ cm}$) and avoiding near-SiPM optical coupling non-linearities. |
| **$c_{\text{scint}}$ Peak Extraction** | Landau fit over wide range without robust fallback when fits failed or diverged. | Adaptive Landau fit ($[mode - 1.5, mode + 3.0]\text{ ns}$) with automated Gaussian fallback and bin mode safeguard. |
| **$c_{\text{scint}}$ Uncertainty** | Purely statistical fit covariance error $\delta c_{\text{fit}} = \sigma_m / m^2$. | Two-fold uncertainty: statistical fit error $\delta c_{\text{fit}}$ plus a 5-segment subrange systematic stability test $\delta c_{\text{syst}}$. |
| **Photon ToF Decoupling** | Depended on `MuFilterCorrectedTime()`, which assumed pre-existing time-walk and alignment parameters, causing crashes. | Cleanly decoupled in `correct_ToF()`, requiring strictly $c_{\text{scint}}$ and track intercept $x_{\text{pred}}$, with safe fallbacks and empty-state initialization. |
| **Time-Walk Fit Optimization** | ROOT Minuit fits prone to parameter divergence or local minima trapping; no systematic floor modeling. | SciPy bounded Levenberg-Marquardt / Trust Region Reflective optimization with dissertation Table 4.2 bounds and adaptive $t_0$ seeds. |
| **Time-Walk Error Modeling** | Standard Error of the Mean (SEM) only, leading to inflated $\chi^2/\nu \sim 40\text{--}100$ due to unmodeled electronics jitter. | Two-stage fit incorporating a Negative Log-Likelihood (NLL) systematic floor $\sigma_{\text{sys}}$, restoring $\chi^2_{\text{tot}}/\nu \approx 1.0$. |
| **Visualization & Canvas Output** | Separate 1D/2D histograms without integrated ratio pads or systematic uncertainty bands. | Publication-quality 2-pad ROOT canvas per channel: Upper pad (70%) with 2D COLZ, statistical SEM points, azure total uncertainty band ($\text{SEM} \oplus \sigma_{\text{sys}}$), and fit curve; Lower pad (30%) with Data/Fit ratio, error bars, and reference unity line. |
| **Reference Systems** | Required selecting either `--referencesystem 3` (DS) or `1` (SciFi), running independent calibrations and storing fragmented outputs. | Automatic dual-reference evaluation: processes both DS ($t_0^{\text{DS}}$) and SciFi ($t_0^{\text{SF}}$) references in parallel in a single loop, eliminating the `--referencesystem` requirement. |
| **Data & Parameter Storage** | Fragmented text files, CSVs, and multiple disparate ROOT and JSON files. | Consolidated hierarchical ROOT file (TDirectory per channel with `_DS` and `_SF` objects) and unified JSON calibration dictionary (`run<runNr>_timing_calibration.json`) containing both `DS` and `SF` blocks (plus top-level aliases). |

---

## 2. Scintillator Signal Propagation Speed ($c_{\text{scint}}$)

### 2.1 Physical Fit Range Alignment with Detector Acceptance
- **Detector Boundaries:**
  - Upstream (US) horizontal scintillator bars extend over $x \in [-78.99, +3.53]\text{ cm}$, with Left SiPMs at $x \approx +3.5\text{ cm}$ and Right SiPMs at $x \approx -79.0\text{ cm}$.
  - Downstream (DS) vertical tracking bars (stations DS1–DS4) span $x \in [-60.65, -1.07]\text{ cm}$.
- **Acceptance Boundary:**
  - Since track reconstruction requires hits in DS vertical bars, muon tracks physically cannot exist at $x < -58\text{ cm}$. In Andrew's original implementation, fitting across $[-80, +5]\text{ cm}$ introduced empty or low-statistics bins with large leverage arms, pulling the linear slope.
  - Furthermore, within $\sim 8\text{ cm}$ of the SiPM coupling face, optical edge coupling non-linearities distort effective propagation time.
- **Modernization:**
  - Standardized default fit range: $\mathbf{[-55.0, -5.0]\text{ cm}}$.
  - This ensures all slices lie well inside active DS tracking coverage while rejecting edge optical effects.

### 2.2 Modal Value (MPV) Extraction & Safeguards
- For each slice in $x_{\text{pred}}$ (bin width $\approx 1\text{ cm}$):
  1. Determine bin mode from the maximum bin in $\Delta t = t_{\text{ref}} - t_{\text{SiPM}}$.
  2. Fit Landau distribution within $[mode - 1.5, mode + 3.0]\text{ ns}$.
  3. Validate fit status and parameter error ($0 < \sigma_{\text{MPV}} < 2.5\text{ ns}$).
  4. If Landau fails or diverges, fall back to Gaussian fit in $[mode - 1.5, mode + 1.5]\text{ ns}$.
  5. If Gaussian fails, record the histogram mode with error $\Delta_{\text{bin}} / \sqrt{12}$.
- This guarantees zero unhandled exceptions or NaN values propagating to the linear fit.

### 2.3 Statistical and Systematic Uncertainty Decomposition
- Linear fit model: $\Delta t(x) = m \cdot x + q$.
- Signal speed:
  $$c_{\text{scint}} = \frac{\pm 1}{m} \quad (+1 \text{ for Left SiPMs, } -1 \text{ for Right SiPMs})$$
- Fit uncertainty:
  $$\delta c_{\text{fit}} = \left| \frac{\sigma_m}{m^2} \right|$$
- **Systematic Stability Evaluation:**
  - The fit region $[-55.0, -5.0]\text{ cm}$ is divided into $N = 5$ equal segments of $10\text{ cm}$ each.
  - Subrange linear fits are performed across each segment to yield local speeds $\{c_1, \dots, c_5\}$.
  - The sample standard deviation across valid subranges is taken as the systematic uncertainty:
    $$\delta c_{\text{syst}} = \text{std}(\{c_s\})$$
  - Final speed is reported and stored as $[c_{\text{scint}}, \delta c_{\text{fit}}, \delta c_{\text{syst}}]$.

---

## 3. Scintillator Photon Time-of-Flight (ToF) Correction

### 3.1 Physics Formulation
Muon track traversal produces scintillation light at coordinate $x_{\text{track}}$, which propagates through the scintillator bar over distance $d_{\gamma} = |x_{\text{track}} - x_{\text{SiPM}}|$ at effective speed $c_{\text{scint}}$:
$$t_{\gamma} = \frac{|x_{\text{track}} - x_{\text{SiPM}}|}{c_{\text{scint}}}$$
The photon ToF-corrected time is then:
$$t^{\text{ToF}}_{\text{SiPM}} = t_{\text{raw}} - t_{\gamma}$$
Subtracting from the downstream reference timestamp $t_{\text{ref}}$ yields the ToF-corrected relative time:
$$\Delta t^{\text{ToF}} = t_{\text{ref}} - t^{\text{ToF}}_{\text{SiPM}}$$

### 3.2 Decoupling from Reconstruction Dependencies
- In Andrew's scripts, calculating $\Delta t^{\text{ToF}}$ routed through `MuFilterCorrectedTime()`, which expected pre-loaded time-walk parameters (`twparameters`) and system alignment constants (`alignmentparameters`), causing fatal crashes when running calibration passes on uncalibrated data.
- **Adaptation:**
  - Implemented direct ToF correction via `self.muAna.correct_ToF()` in `TimeWalk.tof()`.
  - Initialized default empty dictionaries for `twparameters`, `alignmentparameters`, and `cscintvalues` in `AnalysisFunctions.__init__`.
  - Added strict guard in `TimeWalk.tof()`: if a channel has insufficient statistics for $c_{\text{scint}}$ extraction in Pass 1, it is safely bypassed during Pass 2 without breaking execution.

---

## 4. Time-Walk Parameterization & Fitting

### 4.1 Functional Model
The time-walk effect—induced by fixed-threshold discriminator delay as a function of pulse amplitude—is parameterized via the 5-parameter rational function:
$$\Delta t^{\text{TW}}(\text{QDC}) = t_0 + \frac{\alpha}{\beta \cdot \text{QDC} - Q_0} + \gamma \cdot \text{QDC}$$
- $t_0$: Asymptotic time offset at high QDC.
- $\alpha, \beta, Q_0$: Rational curve parameters capturing the steep onset delay at low pulse amplitudes.
- $\gamma$: Small linear term compensating for high-QDC baseline shift or integrator drift.

### 4.2 Parameter Boundary Constraints
Boundaries from Andrew's dissertation (Table 4.2) were implemented with dynamic $t_0$ seeding:
- $t_0 \in [0.5 \cdot t_0^{\text{est}}, 1.5 \cdot t_0^{\text{est}}]$ (where $t_0^{\text{est}}$ is the median relative time for $\text{QDC} > 0.6 \cdot \text{QDC}_{\max}$)
- $\alpha \in [-500.0, 0.0]$
- $\beta \in [0.01, 30.0]$
- $Q_0 \in [-10.0, 0.0]$
- $\gamma \in [0.0, 1.0]$

### 4.3 Systematic Error Floor Determination ($\sigma_{\text{sys}}$)
Because high-statistics runs have very small Standard Error of the Mean ($\text{SEM} = \text{RMS}/\sqrt{N} \sim 10\text{--}30\text{ ps}$), fitting with statistical errors alone produces unphysically large $\chi^2/\nu \approx 40\text{--}100$. This occurs because intrinsic timing jitter and SiPM transit fluctuations establish a physical error floor.
- We implemented a Negative Log-Likelihood (NLL) optimization:
  $$\text{NLL}(\sigma_{\text{sys}}) = \frac{1}{2} \sum_{i} \left[ \frac{(y_i - f(\text{QDC}_i))^2}{\text{SEM}_i^2 + \sigma_{\text{sys}}^2} + \ln(\text{SEM}_i^2 + \sigma_{\text{sys}}^2) \right]$$
- Optimized over $\sigma_{\text{sys}} \in [1, 1000]\text{ ps}$ using SciPy's bounded scalar minimizer.
- This extracts the true systematic error floor ($\sigma_{\text{sys}} \sim 100\text{--}300\text{ ps}$) and adjusts $\chi^2_{\text{tot}}/\nu$ to $\sim 1.0$.

---

## 5. Visual Output: Publication-Quality Two-Pad Canvases

For every calibrated channel, a standardized ROOT `TCanvas` named `c_timewalk_fit_<ref>_<detID>_<SiPM>` (1100 $\times$ 900 px) is generated, reproducing the publication styling:

1. **Upper Pad (72% Height):**
   - 2D histogram $\Delta t^{\text{ToF}}$ vs QDC formatted with bin width of **1.0 QDC** along X and **0.1 ns** along Y (`(200, 0, 200)` $\times$ `(350, -10, 25)`).
   - Rendered using smooth 255-contour rainbow palette (`kRainBow`), with vertical range display $[-10.0, 25.0]\text{ ns}$.
   - Top-left title box (`TPaveText`) showing detector channel and run number.
   - Total uncertainty band ($\text{SEM} \oplus \sigma_{\text{sys}}$) rendered as semi-transparent light sky-blue error boxes (`#99CCFF`, `TGraphErrors` with option `E2 SAME`, alpha 0.45, width $\pm 0.5$ QDC).
   - Statistical data points (black circular markers) with SEM vertical error bars (`P SAME`).
   - Best-fit curve (`TF1`, red line, width 3).
   - Standardized legend in top-left quadrant detailing:
     - Statistical vs Total reduced chi-squared: $\chi^2_{\text{stat}}/\nu \to \chi^2_{\text{tot}}/\nu$.
     - Fit parameters: $t_0$, $\alpha$, $\beta$, $Q_0$, $\gamma$.
     - Systematic error floor $\sigma_{\text{sys}}$ (in ps) and percentage RMS residual.

2. **Lower Pad (28% Height):**
   - Data / Fit ratio ($y_i / f(\text{QDC}_i)$) with vertical range $[0.92, 1.08]$ and 505 divisions.
   - Light sky-blue boxes displaying total relative uncertainty (`AE2`).
   - Black markers displaying statistical SEM uncertainty (`P SAME`).
   - Dashed red reference line at ratio $= 1.00$.

---

## 6. Longitudinal Slices & Propagation Fits

- **Timing Slice Fitting:** Timing differences $\Delta t = t_0 - t_{\text{SiPM}}$ are Gaussian-distributed (convolution of reference, transit, scintillation, and TDC timing jitters), not heavy-tailed Landau distributions. Slices are fitted using a localized Gaussian around the mode, eliminating the tail bias and lowering $\chi^2/\text{ndf}$ from $\sim 3\text{--}4$ down to $\sim 1.0$.
- **Slice Storage (`--saveSlices`):** Optional storage via CLI flag. When enabled, attaches the fit function directly to `GetListOfFunctions()` for automatic visualization in `TBrowser` without generating 25,000 separate canvas allocations.

### 6.1 Unified ROOT File
Output path: `<outputDir>/run<runNr>/timewalk_calibration.root`
- Root level: Global run diagnostics (`reft-DS`, `reft-SF`, `NDSHSiPMs`, `reducedchi2-DS`, `reducedchi2-SF`, `tds0vxpred`).
- Channel Subdirectories: Each channel has its own `TDirectory` (`<detID>_<SiPM>`) containing:
  - Raw 2D histograms (`dtvxpred_<ref>_*`, `dtvqdc_<ref>_*`).
  - Slice MPV extraction graphs (`gr_mpv_<ref>_<channel>`) and mean profiles (`prof_<ref>_<channel>`).
  - Propagation speed linear fit (`fit_cscint_<ref>_<channel>`) and canvas (`c_cscint_<ref>_<channel>`).
  - Time-walk fit function (`fit_tw_<ref>_<channel>`), data graphs (`g_data_*`), ratio graphs (`g_ratio_*`), and complete 2-pad canvases (`c_timewalk_fit_<ref>_<channel>`).
  - **Landau Slices Subdirectory** (`landau_fits_<ref>/`, enabled via `--saveSlices`): Holds individual 1D slice projection histograms (`h_slice_<ref>_<channel>_bx<bx>`) with their fitted Landau/Gauss functions attached to `GetListOfFunctions()`. When opening in ROOT / `TBrowser`, the slice histogram and fitted curve display together without overhead. By default, slice storage is disabled to maximize I/O throughput.

### 6.2 Consolidated Calibration JSON
Output path: `<outputDir>/run<runNr>_timing_calibration.json`
Structured as a single dictionary containing both reference systems (DS and SF) as well as top-level aliases:
```json
{
  "DS": {
    "cscint": {
      "20000_0": [14.42, 0.12, 0.35],
      "20000_1": [14.18, 0.15, 0.28]
    },
    "timewalk": {
      "20000_0": {
        "t0": 8.52,
        "alpha": -31.91,
        "beta": 1.37,
        "qdc0": -8.88,
        "gamma": 0.00299,
        "sigma_sys": 0.1044,
        "chi2_stat_ndf": 41.1,
        "chi2_tot_ndf": 1.05,
        "rms_residual": 0.0135,
        "qdc_limits": [1.0, 180.0]
      }
    }
  },
  "SF": {
    "cscint": {
      "20000_0": [14.45, 0.11, 0.33],
      "20000_1": [14.21, 0.14, 0.26]
    },
    "timewalk": {
      "20000_0": {
        "t0": 3.12,
        "alpha": -30.85,
        "beta": 1.35,
        "qdc0": -8.92,
        "gamma": 0.00310,
        "sigma_sys": 0.0982,
        "chi2_stat_ndf": 38.5,
        "chi2_tot_ndf": 1.02,
        "rms_residual": 0.0128,
        "qdc_limits": [1.0, 180.0]
      }
    }
  }
}
```
All legacy mode switches and duplicate top-level aliases (`"cscint"`, `"timewalk"`) have been eliminated for a clean single-source-of-truth structure.
