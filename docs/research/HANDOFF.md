# Handoff (2026-11-25, 23:30 UTC)

This is everything a new session needs to continue CyberEpi from an empty context.
Read this first, then `docs/research/PROBLEM_BRIEF.md`, `ROADMAP.md` and `SUBMITTING.md`.

## 1. The goal and the owner's standing instructions

- **Goal:** an honest, hard-to-attack flu forecaster submitted live to CDC FluSight
  for 2026-27, scored by the CDC. It is a CV project for the owner (GitHub `avianthonf`).
- **Standing approval:** "in future you do everything". Weekly CDC submissions are
  approved. Decisions inside the owner's own repositories are not asked about.
  Anything else public in the owner's name still needs approval.
- **Style:** the owner prefers short answers. They said "Never stop": keep working
  autonomously on the research program below.
- **Privacy:** the contributor email `avianthonf@protonmail.com` is used only in the hub
  metadata (the owner provided it for that). Treat any other personal details as private.
- **Commits:** no model identifiers in commits or files. End commit messages with the
  Co-Authored-By and Claude-Session lines the session's system reminder gives.
- **Branches:** push to `main` (owner's choice) and mirror to the session branch
  given in the session's instructions.

## 2. Current state

### Live submission
- **Model 1, `CyberEpi-EAKF`** (designated): first submission, reference date 2026-11-28,
  was merged into `cdcepi/FluSight-forecast-hub` (PR #4189, all checks passed).
- **Model 2, `CyberEpi-GBQR`** (not designated): submitted from reference date 2026-12-05.
- **Weekly workflow:** `.github/workflows/weekly-forecast.yml` runs Wednesday 19:30 UTC,
  with a retry Thursday 01:30 UTC. It forecasts both models, commits `forecasts/` to main,
  then opens the CDC pull request from the fork `avianthonf/FluSight-forecast-hub`.
  - The PR step needs the repository secret **`FLUSIGHT_PR_TOKEN`**: a classic token with
    only the `public_repo` scope, expiring 2027-06-30. **The owner was asked to create it;
    not yet confirmed.** Without the secret the step prints a notice and skips.
  - It never resubmits a file that is already in the hub, and never opens a second PR
    for the same week.
- **Today's scheduled run** (2026-11-25, for 2026-11-28) had not started by 19:45 UTC.
  As of 23:30 UTC no forecast commit had reached main, so check the Actions tab. The EAKF file is already in the hub, so it should only commit
  forecasts and skip submission. GBQR is skipped for reference dates before 2026-12-05.
- **Next submission:** Wednesday 2026-12-02 (reference date 2026-12-05), the first week
  with both models. It also adds the GBQR metadata. Check that run.

### Repository cleanup (done today)
- The old platform (patient app, six services, shared libs, infra, deploy, scripts) was
  removed from main. The last commit with it is `509f9dc`. Pushing a tag was blocked
  from the session, so README links to the commit instead.
- CI (`.github/workflows/ci.yml`) is now forecaster-only (lint, imports, scoring tests)
  and passes.

### Session limitations seen
- `add_repo` cannot attach `cdcepi/FluSight-forecast-hub`: it clashes with the fork's
  name. CDC PRs are opened by the workflow (token) or by the owner.
- Tag pushes return 403. Branch pushes to main and the session branch work.
- A stale local `main` existed in a clone; always run `git checkout -B main origin/main`
  after a fetch.

## 3. Research program (the current work)

The owner asked for deep research on every documented technique, unconventional but
sane ensembles (luck-aware; gated by real-world event streams through learned weights),
and old/rare/cross-domain papers, feeding both the CDC submission and a lab.

### Agreed corrections to the owner's plan
1. Do not pick methods by the best score on last season: too few seasons, so it selects
   luck. Develop on 2023-24/2024-25 leave-one-season-out. The 2025-26 holdout is used up.
2. Learned ensemble weights tend to fit luck (the forecast combination puzzle). Shrink
   toward equal weights; trust them only if they win in shadow mode.
3. Run research agents by family (13), not one per technique.

### Two tracks
- **Track A:** changes to what we submit. Needs strong evidence.
- **Track B:** the lab, where anything sane goes. Lab models run in **shadow mode**: live
  every week, committed to git (timestamped), never submitted, scored on 2026-27 data.
  Winners can graduate next season.

### Research agents: status
`docs/research/PROBLEM_BRIEF.md` (committed) is the shared brief every agent reads.
Thirteen background agents were launched, each writing
`docs/research/families/NN-<slug>.md`. **All 13 stopped at the account's 5-hour usage
limit** (reset 22:40 UTC). Only one report was written:

- `12-rare-cross-domain.md` (65 KB), complete (ends with its reference list).

Relaunch the other 12. The families and file names:

| # | File | Family |
|---|---|---|
| 01 | 01-classical-statistical.md | baselines, analogues, ARIMA/ETS, state space, count models, GAM/GP, Delphi methods |
| 02 | 02-mechanistic-structure.md | SIR/SEIR variants, multi-strain, age, metapopulation, humidity forcing, renewal/Rt, curve models, diagnosis of model 1's too-steep decline |
| 03 | 03-data-assimilation.md | KF/EnKF/EAKF variants, inflation, particle filters, IF2, pMCMC, ABC; fixes for undercoverage |
| 04 | 04-tabular-ml.md | GBQR/QRF/NGBoost/GAMLSS, pooling, target transforms, features; model 2 runs low in rises |
| 05 | 05-deep-learning.md | RNN/TCN/N-BEATS/TFT/GNN, physics-informed nets, foundation models (CPU), sim-pretraining |
| 06 | 06-nowcasting-revisions.md | reporting triangle, chain ladder, NobBS/epinowcast, backfill; quantify revisions in time-series.csv |
| 07 | 07-calibration-conformal.md | PIT, isotonic, EMOS, conformal (CQR, ACI, PID), why our post-hoc fix failed |
| 08 | 08-ensembles.md | combination puzzle, QA vs linear pool, stacking, BMA/BPS, expert advice (Hedge, fixed-share), mixture of experts, skill-vs-luck tests; 3–5 novel combiners |
| 09 | 09-external-data.md | ILINet, NREVSS, wastewater, Delphi Epidata (as-of archives), trends, weather, school calendars, strains; event-stream feature design |
| 10 | 10-turning-points.md | predictability limits, early warning signals, changepoints, HMM regimes, peak and rate-change targets; phase analysis of ensemble bias |
| 11 | 11-spatial-hierarchical.md | partial pooling, hhh4, mobility, lead-lag states, reconciliation, small counts |
| 12 | 12-rare-cross-domain.md | Farr, Baroyan-Rvachev, weather MOS/analogues, MIDAS, credibility theory, EDM/S-maps, superforecasting, Elo |
| 13 | 13-scoring-evaluation.md | proper scores, WIS decomposition, CDC evaluation methods, power analysis, shadow-mode protocol |

**Common prompt for each agent:**
> You are one of 13 research agents. First read
> /home/user/CyberEpi/docs/research/PROBLEM_BRIEF.md. Your family: <row above, expanded>.
> For each technique give: (1) deep theory with equations and how uncertainty is
> produced; (2) how exactly it applies to this problem and our models; (3) evidence, with
> citations you actually opened (mark anything unverified), and which FluSight teams use
> it (hub `model-metadata/`); (4) failure modes; (5) cost on a 4-CPU, 30-minute weekly
> budget. Then a ranked list of experiments tagged Track A/B, each with an honest test
> design (no look-ahead, pre-registered, dev seasons leave-one-out, shadow mode). Write
> the report to /home/user/CyberEpi/docs/research/families/<file>; modify nothing else;
> no git. Final message: top 5 recommendations in under 200 words.

Consider spacing the launches to avoid hitting the usage limit again.

### Archive scoring (task in progress)
`backtest/archive_scores.py` (uncommitted until this handoff) scores every team model in
the hub archive (`wk inc flu hosp`, h=0..3, 23 quantiles) against the latest truth. It
writes:
- `rows.parquet`: one row per forecast (not committed);
- `summary.csv`: relWIS vs ensemble and baseline by season, horizon and phase
  (rising / near peak ±2 weeks / declining);
- `pairwise.csv`: the CDC-style pairwise relative WIS per season.

Status:
- WIS was verified against `wis.py`: it equals the sum of the 23 pinball losses ÷ 11.5.
- The first run failed: parquet files have `datetime.date` reference dates. The fix
  (convert dates to strings in `load_model`) is in the file, but the rerun was
  interrupted, so it is unverified.
- It needs `pyarrow` (`pip install pyarrow`).
- The hub copy is at `/home/user/flusight-forecast-hub`: 148 models, 1.8 GB. That path
  won't exist in a new container: clone `https://github.com/cdcepi/FluSight-forecast-hub`.

Run: `python3 -W ignore backtest/archive_scores.py --hub <hub> --out backtest/results/archive --ncpus 4`
(about 2 minutes). Next: classify methods from `model-metadata/*.yml`, and summarise which
method types win, in which phase and at which horizon.

### Shadow mode (task in progress)
`backtest/shadow.py` (uncommitted until this handoff) holds lab models in `MODELS`. Each
writes `forecasts/shadow/<model>/<ref>-<model>.csv`. Two models so far:
- `CyberEpi-MIX_QA`: equal quantile average of EAKF and GBQR;
- `CyberEpi-MIX_LP`: equal linear pool (average the CDFs, then invert).

Tested on 2026-11-28 (53 locations, h=0..3). For the US at h=3, EAKF's median is 14.2k
and GBQR's 27.0k: a large disagreement, which makes it a good live test. GBQR files
have no h=−1.

Still to do:
1. Add a step to `weekly-forecast.yml` after the GBQR run:
   `python3 backtest/shadow.py --forecasts forecasts --reference-date <ref>`, then include
   `forecasts/shadow/` in the commit. It must never block submission (it returns
   non-zero only if every lab model fails; use `continue-on-error: true`).
2. Write `docs/research/SHADOW_PROTOCOL.md` **before any live truth exists** (the first
   scored week is roughly early December). Contents: metrics (WIS, relWIS vs EAKF and vs
   FluSight-ensemble, coverage), tests (e.g. Diebold-Mariano with autocorrelation-robust
   variance, block bootstrap over weeks), the minimum number of weeks before declaring a
   winner, and the graduation rule.
3. Write `backtest/score_live.py`. It scores `forecasts/model-output` and
   `forecasts/shadow` plus the hub's ensemble and baseline against the latest truth,
   writes `results/live/`, and runs weekly in the workflow.
4. Add lab models as the research recommends (luck-aware and event-gated combiners,
   conformal calibration, nowcasting, phase-aware models).

### Task list
1. Problem brief: done.
2. Launch research agents: launched; all hit the usage limit; relaunch needed.
3. Archive scoring: code written; rerun and analyse.
4. Shadow harness: models written; wire the workflow, protocol and live scorer.
5. Synthesis: rank ideas into Track A/B (`docs/research/SYNTHESIS.md`), implement, and
   shadow-run.

## 4. Key facts

- **Honest backtest, model 1:** relWIS vs baseline 0.650 (2024-25) and 0.766 (2025-26);
  vs ensemble 0.966 and 1.163. 90% intervals cover about 74%. It runs low in declines.
- **Model 2:** holdout 2025-26 relWIS 0.385 vs baseline and 0.584 vs ensemble, driven by
  one national peak call. It runs low in rises.
- **The 2026-27 season is early:** US admissions 13.7k on 2026-11-21 and rising.
- **Hub targets 2026-27:** `wk inc flu hosp` (quantiles, samples), `wk flu hosp rate
  change` (pmf, 5 categories), `peak week inc flu hosp`, `peak inc flu hosp`,
  `wk inc flu prop ed visits`. We submit only the first so far.
- **Key files:** `backtest/live.py` (weekly entry point), `eakf.py`, `seir_fast.py`,
  `gbqr.py`, `run_vintage.py` (as-of backtest), `hub_data.py`, `package_submission.py`,
  `validate_submission.py`, `wis.py`, `model_config.json`, `model2_config.json`.
