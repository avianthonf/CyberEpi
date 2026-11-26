# Family 05: Deep learning and foundation models for weekly influenza forecasting

Scope: RNN/TCN/N-BEATS/TFT/GNN, physics-informed networks (PINNs), CPU-runnable time-series foundation models (TSFMs), simulation pretraining on SEIR, and which FluSight teams use deep learning (DL). Context: 53 locations, horizons 0..3 weeks, WIS scoring. Our models: CyberEpi-EAKF (SEIR ensemble Kalman filter, 300 members) and CyberEpi-GBQR (pooled LightGBM quantile regression). The 2025-26 holdout is spent. Track A = submission change (strong evidence needed). Track B = lab/shadow only.

Labels: [MEAS] measured here; [QUOTED] from a cited source; [OBS] from repo or hub data; [INFERENCE] reasoning; [UNVERIFIED] not checked.

---

## 1. Theory and how uncertainty is produced

**Architectures.**

- *Recurrent / convolutional.* Recurrent hidden state h_t = f(h_{t-1}, x_t). A temporal convolutional network (TCN) uses dilated causal convolutions with receptive field about k·2^L. Bai, Kolter & Koltun (2018) found a generic TCN often matches LSTM/GRU [QUOTED: arXiv:1803.01271].
- *N-BEATS.* Fully connected blocks with backcast/forecast residuals; the interpretable variant uses trend and seasonality bases [QUOTED: arXiv:1905.10437].
- *TFT.* Gated residual networks, variable selection, LSTM encoder/decoder, interpretable attention; quantile outputs [QUOTED: arXiv:1912.09363; IJF 2021].
- *GNN.* Message passing H^(l+1) = σ(Â H^(l) W^(l)) over a graph (e.g., transfer-entropy links). Used by UVAFluX-CESGCN [OBS].
- *Foundation models.* Chronos-2 (120M encoder-only, quantile outputs) [QUOTED: HF card]; TimesFM 2.5 (200M decoder-only, 10 outputs) [QUOTED: HF README]; TiRex (35M xLSTM) [QUOTED: NX-AI repo]. Simulation-pretrained models: Mantis, SGNN, CAPE (§3).

**Probabilistic output.**

- Pinball loss at quantile q: L_q(y, ŷ_q) = max(q(y−ŷ_q), (q−1)(y−ŷ_q)). Averaging over the FluSight quantile set gives a loss close to WIS.
- Parametric heads (negative binomial, gamma) give predictive distributions by construction (CU-ARNB_Net, OHT_JHU-nbxd).
- Uncertainty is aleatoric when the head learns noise. Epistemic uncertainty needs ensembles (seeds, MC dropout) or conformal calibration (UM-DeepOutbreak uses neural conformal control). Single-seed quantile nets tend to be under-dispersed on held-out seasons, consistent with the low coverage in §3.

**PINNs.** Minimise L = L_data + λ·L_ODE, where L_ODE penalises the residual of the SEIR system at collocation points; β, σ, γ can be inferred jointly [QUOTED: arXiv:2110.05445; EINN, Rodríguez et al. 2023, cited in SGNN]. The constraint biases the fit when the ODE is misspecified or reporting is noisy. SGNN reports a SEIR-PINN skill of −112 on early COVID data [QUOTED: arXiv:2507.08977; author-reported].

---

## 2. Application to this problem and our models

- **Data size.** 53 locations × ~2 seasons of weekly points is about 1,000 points per location. Too few for a per-location LSTM/TFT without priors. Pooled models (like GBQR) are the realistic DL setting.
- **Model 1 (EAKF).** Already mechanistic. A PINN would duplicate it. The useful DL role is an *emulator* of the forward step (B4), or learning β(t). Track B.
- **Model 2 (GBQR).** A small pooled quantile TCN/MLP on the same features is the like-for-like DL test (B3).
- **Known gap.** Model 2 runs low on rises, model 1 on declines. The archive phase numbers in §3b do not show DL fixing either.
- **Zero-shot TSFMs** need no training on our data and are the cheapest DL route. Risk: they do not know flu seasonality or reporting artifacts.

---

## 3. Evidence

### 3a. Hub DL teams [OBS]

Keyword grep of `model-metadata/` (159 yml files) matched 40 files. Keyword matches are candidates, not confirmed DL; several are ensembles or GLEAM mechanistic models with a DL-named component. Full list of 40:

ACCIDDA-Chromantis, ACCIDDA-insightcast, CADPH-FluCAT_Ensemble, CU-ARNB_Net, CU-STS_Residual, CU-STS_base, CU-ensemble, DMAPRIME-HYB, Emory-EpiRSI, FluTurists-ensemble, GT_Influencers-ensemble, Gatech-ensemble_point, Gatech-ensemble_prob, JHU_CSSE-CSSE_Ensemble, JPAT-FluGBM, LosAlamos-ThinMint, MOBS-EpyStrain_Flu, MOBS-GLEAM_NCB_FLUH, MOBS-GLEAM_PONG, MOBS-GLEAM_RL_FLUH, NAU-FourCAT, NEU_ISI-AdaptiveEnsemble, NEU_ISI-FluBcast, NU-EMBERS, NU_UCSD-GLEAM_AI_FLUH, OHTJHU-BM, OHT_JHU-nbxd, SahilLab-Trio, Schnitzels-stack5, UI_CompEpi-EpiGen, UM-DeepOutbreak, UMass-axial_r2, UNC_IDD-InfluPaint, UVAFluX-CESGCN, UVAFluX-Ensemble, UVAFluX-OptimWISE, VTSanghani-Ensemble, VTSanghani-PRIME, Xi_lab-GLEAM_AI, Xi_lab-GLEAM_AI_hybrid.

Roles seen in metadata (selected):
- Foundation models: ACCIDDA-insightcast (NNETAR + Chronos/TimesFM/Sundial, WIS-selected); CU-STS (Chronos-2 + TimesFM-3.0 + LightGBM + SARIMAX); OHTJHU-BM (median of Chronos-2, TimesFM 2.5, Moirai 2.0-R-small, Timestral); Emory-EpiRSI (frozen Chronos-2, TimesFM-3, Toto-2 + boosted trees); Xi_lab-GLEAM_AI_hybrid (TimesFM 2.0/3.0 on a GLEAM-AI surrogate).
- Trained nets: ACCIDDA-Chromantis; CU-ARNB_Net (negative binomial); DMAPRIME-HYB (CNN-LSTM, 3 seeds); FluTurists-ensemble (small TFT); JHUAPL-Morris (N-HiTS; not in the 40 list, from earlier survey); JHU_CSSE (LSTM by cluster); LosAlamos-ThinMint (transformer); NAU-FourCAT (Fourier calendar-aware transformer); OHT_JHU-nbxd (N-BEATS + TCN covariates, gamma); SahilLab-Trio (GRU, 5 seeds); UMass-axial_r2 (transformer pretrained on simulated flu seasons, then fine-tuned); UVAFluX-CESGCN (GNN); UM-DeepOutbreak (diffusion + transformer); UNC_IDD-InfluPaint (diffusion); Gatech-ensemble_prob (attention); GT_Influencers-ensemble (CNN); UI_CompEpi-EpiGen (VAE synthetic data).
- Simulation / RL hybrids: MOBS-GLEAM_* (RL/bandit over GLEAM trajectories); NU_UCSD-GLEAM_AI_FLUH.

### 3b. Archive scoring of DL teams [OBS]

Source: `backtest/results/archive/summary.csv`, ArchiveScorer output. **Filter applied:** ref == FluSight-ensemble only (the file also holds FluSight-baseline rows, which were mixed in earlier and inflated the medians), by == season or season+phase, and n ≥ 300 weekly scored rows per model-season. DL = models tagged `deep_learning=1` in `method_types.csv` (28 models in the filtered set; 89 non-DL). Values are rel WIS, so >1 is worse than the ensemble.

Season medians (model-season rows; n = number of model-season rows):

| Season | DL median rel (n) | non-DL median rel (n) |
|---|---|---|
| 2023-24 | 1.358 (7) | 1.295 (30) |
| 2024-25 | 1.285 (11) | 1.099 (36) |
| 2025-26 | 1.342 (11) | 1.226 (43) |
| 2026-27 (partial, few weeks) | 1.206 (18) | 1.382 (54) |

Phase medians, pooled 2023-26 season+phase rows (2026-27 excluded because it is partial; n = rows):

| Phase | DL (n) | non-DL (n) |
|---|---|---|
| rising | 1.213 (22) | 1.091 (96) |
| near_peak | 1.124 (28) | 1.133 (102) |
| declining | 1.518 (28) | 1.321 (104) |

Reading (keyword-flagged models, unconfirmed): over 2023-26, the flagged set is worse than non-DL in three of four season slices and in rising and declining phases. Near-peak is a tie. The flag comes from keyword matching in `method_types.csv` and includes ensembles and GLEAM hybrids, so these are not confirmed DL results. The 2026-27 flagged advantage rests on 18 model-season rows from a few weeks of data and should not be used for a decision.

Individual DL rows (ensemble ref, n ≥ 300, season-level): OHT_JHU-nbxd 0.860 (2025-26, cov90 0.685); NAU-FourCAT 0.919 (2025-26, cov90 0.770); Gatech-ensemble_prob 0.930 (2026-27, partial, cov90 0.925); CU-ARNB_Net 1.030 (2025-26); UNC_IDD-InfluPaint 1.031 (2024-25, cov90 0.285); ACCIDDA-Chromantis 1.032 (2026-27, partial). For context, the overall best non-DL rows include UMass-flusion 0.779 (2023-24), Epistorm-Ensemble_Flu 0.844 (2025-26), and UGuelph-CompositeCurve 0.865 (2024-25).

Coverage: several DL teams are poorly calibrated (cov90 0.29 for InfluPaint, 0.31 for UVAFluX-CESGCN in 2024-25). This is a calibration issue as much as a point-skill issue.

Note: an earlier draft cited best DL values of 0.36–0.43 and season medians that pooled two references. Those numbers were wrong and are withdrawn.

### 3c. Literature [QUOTED unless marked]

- **Epidemic TSFM comparison** (Jafari et al., arXiv:2606.19560, June 2026): on 1–4-week influenza forecasts (ILINet, hospitalisations, 10 US regions), a mixture of pretrained forecasters was best; numerical transformers were reliable; pretraining gains were largest at longer horizons when the pretraining domain was mechanistically aligned; LLM-based methods underperformed. Abstract only opened; numbers not checked.
- **SGNN** (Dudley et al., arXiv:2507.08977v4): GNN pretrained only on SEIR-family simulations; reports about 3× median CDC Hub skill on early COVID mortality, 12× over Chronos, better than a SEIR-PINN. Ablations: neural-simulator and SEIR-only pretraining both do worse. Author-reported, COVID-era.
- **Mantis** (arXiv:2508.12260): transformer pretrained on >400M synthetic outbreak-days; zero-shot; competitive on influenza hospitalisation WIS. Author-reported.
- **UMass axial transformer:** hub metadata only; primary paper not read [UNVERIFIED].
- **TDEFSI** (arXiv:2002.04663): LSTM trained on synthetic SEIR output; same idea, older.
- **SIR-INN** (arXiv:2506.03897): SIR-embedded PINN, Italian influenza 2023–25; reported competitive; one country.
- **DINN** (arXiv:2110.05445) and Long et al. (arXiv:2103.09949): PINN parameter inference on COVID-era data; neither benchmarked against a non-physics baseline on flu WIS.

### 3d. Foundation models: code and weights licences, native quantiles, CPU timing

Licences are given separately for code and weights, because they can differ.

| Model | Code licence | Weights licence | Size | Native quantile levels | Source |
|---|---|---|---|---|---|
| Chronos-2 (amazon/chronos-2) | Apache-2.0 [QUOTED: README] | Apache-2.0 [QUOTED: HF card] | 120M | native model levels: 21 (0.01, 0.05, 0.1, …, 0.9, …, 0.95, 0.99); pipeline returned all 23 requested levels incl. 0.025 and 0.975 by interpolation [MEAS] | measured |
| chronos-bolt-small | Apache-2.0 [QUOTED] | Apache-2.0 [UNVERIFIED: not opened] | small | 9 levels: 0.1..0.9; levels outside are clipped to 0.1/0.9 [MEAS] | measured |
| TimesFM 2.5 (google/timesfm-2.5-200m-pytorch) | Apache-2.0 [QUOTED: README] | Apache-2.0 [QUOTED: README] | 200M | mean + 9 deciles; continuous-quantile head can give other levels [MEAS] | measured |
| TiRex (NX-AI/TiRex) | NXAI Community License [QUOTED: summary] | NXAI Community License [QUOTED: summary] | 35M | 9 levels 0.1..0.9 [MEAS] | measured |
| Moirai 2.0-R-small | Apache-2.0 for uni2ts code [QUOTED: summary] | CC BY-NC-4.0 [QUOTED: HF card, summary] | ~11M | 9 levels 0.1..0.9 [QUOTED] | not measured |
| Toto 2.0 | Apache-2.0 [QUOTED: summary] | not checked | 4M–2.5B | quantile outputs [QUOTED] | not measured |
| Lag-Llama | Apache-2.0 [QUOTED: LICENSE] | Apache-2.0 [UNVERIFIED] | ~2.5M | not checked | not measured |

Licence notes:
- TiRex: the NXAI Community License has terms that restrict some uses, including a commercial carve-out above a revenue threshold. Reviewer raised an EU AI Act high-risk exclusion. **That clause was not read in this report**, so I cannot say whether public-health forecasting falls under it. Treat as open until the licence text is read.
- Moirai 2.0 weights are non-commercial. Not usable in any commercial path. Our submission is research use, but the lab should not depend on it without checking the terms.

**CPU timing, measured** (scratch venv `/tmp/tsfm_bench/v311`, Python 3.11, `torch.set_num_threads(4)`, macOS arm64, CPU only). Workload: 53 series, context 104 weekly points from `target-hospital-admissions.csv`, horizon 4, median of 3 repeats (1 for TimesFM/TiRex). Load time includes first-time weight download where it occurred.

| Model | Load (s) | Inference, 53 series × h=4 (s) | Note |
|---|---|---|---|
| Chronos-2 (120M) | 131.7 | 0.125 | 23 requested levels returned; 21 native |
| chronos-bolt-small | 16.4 | 0.038 | 9 native levels; 0.01–0.05 and 0.95–0.99 clipped |
| TimesFM 2.5 (200M), context 256 | 89.9 | 6.19 | compiled config; 10 outputs |
| TiRex (35M) | 1.1 | 4.62 | context 104 |

All four inference times are [MEAS]. Load times are [MEAS] but include cache effects. The 2–7 s range for TimesFM and TiRex is far below the 30-minute budget; the weekly cost is dominated by one-time load, not inference.

Quoted GPU throughput: Chronos-2 >300 series/s on an A10G [QUOTED: HF card]. Not our hardware; ignore for CPU planning.

Quantile extrapolation: the FluSight set needs 0.01, 0.025, 0.975 and 0.99. Chronos-2 covers 0.01 and 0.99, but not 0.025 or 0.975. Bolt, TimesFM and TiRex do not cover the outer levels, so those must be extrapolated (e.g., from the 0.05/0.95 or 0.1/0.9 quantiles with a fitted tail). This affects WIS directly, since outer quantiles weight the tails. Any TSFM submission must document the extrapolation rule and evaluate it on the held-out seasons.

---

## 4. Failure modes

1. **Overfitting to a few seasons.** Two seasons × 53 locations is little signal; DL models fit season shape.
2. **Under-dispersion.** Single-seed quantile heads are over-confident; cov90 down to 0.29 in the hub.
3. **Zero-shot mismatch.** TSFMs trained on generic series do not know flu seasonality or reporting lags.
4. **Look-ahead in pretraining.** Pretraining on real data overlapping test seasons. Our pretraining must use simulation only.
5. **Simulator misspecification.** SEIR-only pretraining gave biased forecasts in SGNN's ablation (author-reported).
6. **Quantile gaps.** Models that do not output the 0.025/0.975/0.01/0.99 levels need extrapolation, which can move WIS.
7. **Peak-timing error.** DL is also worse on declines (1.518 vs 1.321), so DL is not a fix.
8. **Licence drift.** Non-commercial weights (Moirai 2.0) or community licences with carve-outs (TiRex).

---

## 5. Cost on 4 CPUs within a 30-minute weekly budget

- **Inference** for all four measured models is under 10 s per weekly run (§3d). Well inside budget.
- **One-time load** is 1–132 s per model; download-dependent. Cache weights once.
- **Custom LSTM/TCN/TFT** trained weekly on 53 pooled locations: [INFERENCE] 2–5 min per refit on 4 cores for under 10k parameters. Feasible, but the refit is the cost. Not measured.
- **Simulation pretraining:** [INFERENCE] hours of offline compute, not weekly. Must sit outside the budget.
- **Binding costs** are licence review, repeated leave-one-season-out backtests, and any weekly retraining, not inference.

---

## 6. Ranked experiments

All experiments: pre-registered before running; leave-one-season-out on 2023-24 and 2024-25 (2025-26 spent); no look-ahead; shadow-mode forecasts logged weekly before outcomes are known. Metric: relative WIS vs the FluSight ensemble and vs CyberEpi-GBQR, by phase, with n reported.

**Track B (lab/shadow only)**

1. **B1. Zero-shot TSFM member.** Chronos-2 (Apache-2.0 weights) and TimesFM 2.5 (Apache-2.0 weights), no fine-tuning. Use the extrapolation rule in §3d for missing levels. Pass rule: rel WIS < 1.0 on both held-out seasons and cov90 in 0.85–0.95. Cost: seconds per run.
2. **B2. Simulation-pretrained TSFM (Mantis-style).** Pretrain a small transformer or TCN on synthetic SEIR-family outbreaks with seasonality and reporting delay, no real data. Pass rule: beats B1 on rising phase by ≥5% rel WIS on both held-out seasons.
3. **B3. Pooled quantile TCN (Model 2 analogue).** Same features as GBQR, 23 quantiles, 3-seed ensemble, per-horizon conformal recalibration. Pass rule: rel WIS < GBQR on both held-out seasons; cov90 0.85–0.95.
4. **B4. Neural emulator for Model 1.** Small net maps (β, σ, γ, initial state) to the 4-week trajectory, replacing the EAKF forward step. Pass rule: emulator error < 5% of the WIS gap on held-out seasons.
5. **B5. Physics-informed SEIR residual net.** Only if B4 works. Expect poor results under noise (SGNN reports −112 for a PINN); kill criterion set in advance.

**Track A (submission changes; needs strong evidence)**

6. **A1. DL in the ensemble.** Add the B1 or B3 winner with inverse-WIS weights fitted on leave-one-season-out only. Pass rule: improves ensemble rel WIS on both held-out seasons and does not worsen coverage. Do not promote on one season.
7. **A2. Calibration for any DL member.** Per-horizon conformal calibration before inclusion. Precondition for A1.

Only A1 can change the submission. Everything else stays Track B until A1's pass rule holds on both seasons.

---

## Citations

Status: [QUOTED] = opened or from a search summary; [MEAS] = measured here; [UNVERIFIED] = not checked.

1. Bai, Kolter, Koltun (2018). TCN. arXiv:1803.01271. [QUOTED]
2. Oreshkin et al. (2019). N-BEATS. arXiv:1905.10437. [QUOTED]
3. Lim et al. (2021). TFT. arXiv:1912.09363; IJF 37(4). [QUOTED]
4. Jafari et al. (2026). arXiv:2606.19560. [QUOTED: abstract only]
5. Dudley et al. (2026). SGNN, arXiv:2507.08977v4. [QUOTED: opened]
6. Ansari et al. (2025). Chronos-2, arXiv:2510.15821; HF amazon/chronos-2 (Apache-2.0). [QUOTED: README opened]
7. TimesFM 2.5, google/timesfm-2.5-200m-pytorch, HF README (Apache-2.0). [QUOTED]
8. NX-AI TiRex licence, github.com/NX-AI/tirex. [QUOTED: summary; clause not read]
9. Moirai 2.0-R-small model card (CC BY-NC-4.0). [QUOTED: summary]
10. Lag-Llama LICENSE (Apache-2.0). [QUOTED]
11. Mantis, arXiv:2508.12260. [QUOTED]
12. Raissi, Perdikaris, Karniadakis (2019). PINNs. J. Comput. Phys. 378:686–707. [QUOTED: cited in SGNN; DOI not checked]
13. DINN, arXiv:2110.05445. [QUOTED]
14. SIR-INN, arXiv:2506.03897. [QUOTED]
15. Toto 2.0 (Datadog), Apache-2.0. [UNVERIFIED: summary only]
16. CAPE, KDD 2025, dl.acm.org/doi/10.1145/3770855.3818928. [UNVERIFIED: summary only]
17. Decathlon Chronos-2 CPU case study (ag4news). [UNVERIFIED: secondary; not used for numbers]
18. Chronos-Bolt small licence (amazon/chronos-bolt-small). [UNVERIFIED: not opened]

Repo and hub evidence: `model-metadata/` (159 files; 40 keyword matches listed in §3a); `backtest/results/archive/summary.csv` and `method_types.csv` (ensemble ref, n ≥ 300). Benchmark script: `/tmp/tsfm_bench/bench.py` (scratch, outside repo).

## Top 5 (for Main)

1. Run B1 (Chronos-2 + TimesFM 2.5 zero-shot, shadow mode): inference is under 10 s on 4 CPUs, weights are Apache-2.0.
2. Do not promote any keyword-flagged DL model to Track A. The flag is unconfirmed; the archive comparison is suggestive only (rising 1.21 vs 1.09, declining 1.52 vs 1.32), and coverage is poor for several flagged teams.
3. Settle the 0.025/0.975 extrapolation rule before any TSFM run. It moves WIS.
4. Read the TiRex NXAI clause (EU AI Act exclusions) before any use. Moirai 2.0 weights are non-commercial.
5. Keep B5 (PINN) kill-first; pursue B2 (simulation pretraining) only if B1 fails on rises.
