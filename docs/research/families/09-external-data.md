# Family 09: External data for the weekly NHSN admissions forecasts

Owner: R09ExternalData-2. Scope: ILINet, NREVSS clinical labs, NSSP ED visits, NHSN admissions (as a versioned input), NWSS and WastewaterSCAN wastewater, search trends, weather, school calendars, strain/subtype data, and an event-stream feature design for gated ensembles. Target: weekly NHSN influenza admissions, h=0..3, 53 locations (`docs/research/PROBLEM_BRIEF.md`). Models in scope: `CyberEpi-EAKF` (NSSP ED fraction) and `CyberEpi-GBQR` (log ED fraction). The 2025-26 holdout is spent; development seasons are 2023-24 and 2024-25, tested leave-one-season-out.

Labels: **[V]** verified by a live call in this session; **[D]** read in documentation or a paper (via fetch or search summary as noted); **[I]** inference; **[U]** unverified, with reason.

---

## 0. Corrections to the earlier draft

- **covidcast `as_of=` works.** The earlier "silent ignore" finding was wrong. Live check: nssp `time_values=202530&as_of=202545` returns issue 202545 (lag 15); nhsn `as_of=202545` returns issue 202539 (value 869). Both differ from the latest issues (nssp 202638, nhsn 202637). `issues=202545` for nhsn returns "no results" because no revision was published in that exact issue; `issues=` is an exact-match filter, `as_of=` is a latest-on-or-before filter. [V]
- **V4 covidcast is frozen, not live for 2026-27.** Delphi documents V4 covidcast as retired: queries with `time_values`, `issues`, or `as_of` after 2026-09-22 return HTTP 410 [D, Delphi covidcast V4 page]. Our calls still answer because they point to pre-cutoff dates. Latest V4 issues are nssp 202638 and nhsn 202637, about 7 epiweeks behind fluview issue 202645 [V]. Do not use V4 covidcast for 2026-27 work.
- **V5 is the live as-of path.** Base: `https://delphi.cmu.edu/epidata/v5/` (not `api.delphi.cmu.edu`, which returns 404 for `/v5/`). Endpoints: `snapshot/`, `archive/`, `aux_data/`, `metadata/` [D, V5 pages; V5 queries page]. Verified live: see §2.
- **Endpoint names.** Earlier 404s were for guessed legacy names (`nrevss_clin`, `nssp`, `nhsn`, `wastewater`, `nwss`, `nidss_diag`, `fluview_locations`) on the legacy path. They do not show the endpoints are absent. The current V5 source codes are `fluview_ilinet`, `fluview_resp_lab_clinical`, `fluview_resp_lab_ph`, `nrevss`, `nssp`, `nhsn`, `nwss`, `nchs_mortality`, `flusurv`, and others [D, V5 sources table]. There is no `nrevss_*` legacy endpoint to call. Confirm names against `cmu-delphi.github.io/delphi-epidata/api/`.
- **Wastewater.** Legacy wastewater endpoints are not needed: V5 serves `nwss` (§2.4).

---

## 1. Theory

### 1.1 Why external data can help

Let $y_{t,\ell}$ be weekly NHSN admissions at location $\ell$ and epiweek $t$. The target at horizon $h$ is $y_{t+h,\ell}$, forecast from the information set $\mathcal{F}_t$ available at issue time. External signal $x^{(k)}_{t}$ helps only if

$$I\big(y_{t+h};\, x^{(k)}_{t} \mid \mathcal{F}_t\big) > 0,$$

where $\mathcal{F}_t$ is the vintage-correct information set. Three mechanisms:

1. **Lead.** Wastewater and some search signals may lead admissions. Schoen et al. [D] report wastewater influenza A peaks 2–14 days before hospital peaks across 163 WastewaterSCAN plants. A signal leads by $L$ weeks, so it helps at $h > L$ only if it is available at $t$.
2. **Different populations.** ILINet (outpatient ILI visits, weighted to national totals; ILI = fever ≥100°F with cough and/or sore throat [D, CDC FluView overview]) and NREVSS (clinical lab NAAT positivity [D]) measure different populations. Their disagreement carries information on test-seeking and sampling.
3. **Exogenous drivers.** Absolute humidity and school calendars change transmission. Shaman and Kohn [D] report absolute humidity explaining about 50% of transmission variability and 90% of survival variability in guinea-pig reanalysis, against 12% and 36% for relative humidity. School holidays: England and Wales [D] estimate a 17% reduction in the contact parameter for ages 5–14 (95% CI 9–25%) with year-to-year heterogeneity; France [D] estimates a 20–29% reduction in child transmission.

### 1.2 Vintage and look-ahead

For each signal the forecast uses the value as published on or before issue date $\tau_t$:

$$x^{(k)}_{t}\big|_{\text{vintage}} = x^{(k)}_{t}\big(\text{as of } \tau_t\big).$$

Revisions are material. NHSN and NSSP values change across issues [V: nhsn 202530 = 869 at issue 202539, 877 at issue 202546, 892 at issue 202637]. NWSS WVAL is non-normalized since August 2025 and winsorized at the 99th percentile since August 2026 [D, CDC NWSS data-methods]. Backtests must read a stored vintage (V5 `archive/` or `snapshot/` with a fixed `snapshot_date`), not the latest series.

### 1.3 Event-stream features and gating

Each source emits events $e = (k, \tau_e, \lambda, v_e)$. Features at issue time $t$:

$$\phi_{k,j}(t) = \sum_{e:\; t-w_j < \tau_e \le t} \omega_j(t-\tau_e)\, v_e, \qquad w_j \in \{1,2,4\}\text{ weeks}.$$

Gating weights are a softmax over reliability scores computed from past vintages only:

$$g_k(t) = \frac{\exp(s_k(t))}{\sum_{k'}\exp(s_{k'}(t))}, \qquad \hat y_{t+h} = \sum_k g_k(t)\, f_k(\mathcal{F}_t, x^{(k)}_t).$$

Scores are shrunk toward the mean, $s^{\text{shr}}_k = (1-\alpha)s_k + \alpha\bar s$, with $\alpha = K/(K+n_{\text{eff}})$. $n_{\text{eff}}$ counts independent seasons, not weeks. With two development seasons, $\alpha \ge 0.5$ for any $K \ge 2$, so gating starts close to equal weights. Acceptance uses a paired season-level difference with a permutation test over season-label swaps, one-sided $p<0.1$, because two seasons cannot support stricter thresholds.

### 1.4 Uncertainty

With two independent development seasons, season-level variance dominates weekly sample size. Treat any gain smaller than one SD of the season-level paired difference as noise.

---

## 2. Application to our models

### 2.1 NSSP ED and NHSN (Track A input, in production)

- **V5 `nssp`**, signal `pct_ed_visits_influenza`, `geo_type=nation`: snapshot and archive both return data [V, `snapshot/` with `snapshot_date=2025-11-14` returns rows with report_time ≤ that date; `archive/` returns revision rows with report_time up to 2026-11-18]. Use V5 as the as-of source for model 1 and model 2 inputs.
- **V5 `nhsn`**, signal `confirmed_admissions_flu_ew`: snapshot and archive both return data [V]. Archive contains multi-vintage rows for each reference week.
- Resolution: nssp values are reported at 0.1 precision in some summer weeks [V, V4 check]; difference below 0.1 is noise.

### 2.2 ILINet (Track B; as-of confirmed)

- V5 source `fluview_ilinet`, signal `ili` (plus `wili`): `snapshot/` returns rows with `age_group` [V]. V4 `fluview` with `issues=` also returns the as-of value (national epiweek 202540: issue 202545 ili 1.55136; latest 202645 ili 1.54835) [V].
- National ILI baseline 2025-26: 3.1% [D, CDC FluView overview]. Week-on-week change is "stable" within ±0.1 points [D].

### 2.3 NREVSS clinical labs (Track B)

- V5 `fluview_resp_lab_clinical` and `nrevss` (respiratory tests and percent positivity) [D, V5 sources table]. Legacy V4 `fluview_clinical` returns percent_positive and total_specimens with `issues=`, e.g., issue 202545: 0.52512; latest: 0.524646 [V].
- Clinical-lab percent positive is biased by pre-selected positives [D, CDC FluView overview]. Use as an intensity-change signal, not a community-incidence level. Public-health labs (`fluview_resp_lab_ph`) are separate.
- Model-metadata (self-reported): OHT_JHU-nbxd, UMass-peakGB, GT_Influencers-ensemble, Emory-EpiRSI.

### 2.4 Wastewater (Track B)

- **V5 `nwss`** [V]: metadata lists flu signals `flu_avg_conc`, `flu_avg_conc_lin`, `flu_flowpop_lin`, `flu_h5_avg_conc`, `flu_h5_avg_conc_lin`, `flu_h5_flowpop_lin`, `flu_h5_mic_lin`, `flu_mic_lin`. Live snapshot checks (`geo_type=state`): `flu_avg_conc_lin` at `snapshot_date=2025-11-14` and `2026-11-21` returned the CSV header only (0 rows); `flu_avg_conc` returned the header only. The earlier `pcr_conc_smoothed` name is not in the list, which explains its empty result. Metadata reports reference_time 2020-01-14 to 2026-11-17 and report_time 2026-02-25 to 2026-11-20, so the source is populated. The empty snapshots are unexplained; the likely cause is the state-level geo filter or the sewershed-level layout, not the signal name. Not resolved; use `geo_type=county` or `metadata/geo_signals/?source=nwss` to find the populated level before any pull. Anonymous snapshot limit is 3 requests/minute [D], so run a single query per minute.
- **Socrata** `data.cdc.gov/resource/2ew6-ywp6.json` returns sewershed-level rows with dates, population served, and detection fields [V]. The `api/views/.../revisions.json` path returned "No service found" [V], so **Socrata has no visible revision history**. Use dated pulls, stored with retrieval dates, as the only vintage mechanism for that file [I].
- **WastewaterSCAN** (`data.wastewaterscan.org`) reachable [V]; payload check not yet done. Treat as public, dated pulls only [I].
- Lead evidence: Schoen et al. [D] (lead 2–14 days); California EID 2026 [D] (Kendall τ 0.57–0.66, no consistent lead); Michigan/Ontario EID 2024 [D] (ρ 0.77–0.79, mostly synchronous or lagging). OFID 2025 [D, abstract] reports wastewater predicting hospitalizations.
- NWSS WVAL: 24-month site baselines, 8-week minimum window, log transform, state and national medians [D].

### 2.5 Search trends

- Google Health Trends (`ght`) returns 401 on this key [V]. Delphi documents a pause after 2022-09-10 [D, ght page] and a Google discontinuation in March 2021 [D, Delphi milestones page]. The sources conflict on the date, but neither offers a 2025-26 series. **Treated as unavailable.**
- Google Flu Trends failed in 2013 (Lazer et al. 2014 [D]). ARGO-style regularized search models help only with lagged clinical covariates (Yang, Santillana, Kou 2015 [D]). Santillana et al. 2015 [D] found ensembles beat single sources at 1–4 week horizons.

### 2.6 Weather

- Open-Meteo historical ERA5: CC-BY 4.0; free tier non-commercial, 10,000 calls/day; historical data requires a paid plan [D, Open-Meteo pricing and terms, search summaries]. Confirm licence before any production use. Fetch once per location per season and cache.
- Absolute humidity from temperature and relative humidity (Magnus formula). Shaman and Kohn 2009 [D].

### 2.7 School calendars

- Evidence: England and Wales [D, Lancet 2013]; France [D, Nature 2008]; China, RR 0.34 (95% CI 0.29–0.40) for ages 5–19 [D, IJID 2024]; Arizona closures [D, PMC2966666]; Guangzhou [D, BMJ Open 2024]; US winter holidays [D, JID 2017].
- Feature: "school in session" indicator per state, with a holiday-week flag, from versioned state calendars. Default: fixed calendar.

### 2.8 Strain and subtype

- CDC FluView reports subtype proportions weekly [D]. Model-metadata: MOBS-EpyStrain_Flu, NAU-ABERT, cfa-flumech (self-reported). Subtype shifts change severity; treat as a season-level covariate, not a weekly feature.

### 2.9 Event-stream design for gated ensembles (Track B)

1. One stream per source, with `report_time` as the issue time. Pull from V5 `archive/` (or `snapshot/` at fixed dates) and store the pull date.
2. Aggregates $\phi_{k,j}(t)$ for $w_j \in \{1,2,4\}$; standardize with past seasons only.
3. Per-source models $f_k$ (ridge or GBQR) fitted on dev seasons only.
4. Shrunk softmax gate (§1.3), starting at equal weights.
5. Promote only after the §6 test passes.

---

## 3. Evidence

Opened or checked in this session:

- Live: V5 `snapshot/` and `archive/` for `nssp`, `nhsn`, `fluview_ilinet`; V5 `metadata/?source=nwss`; V4 covidcast `as_of=` and `issues=`; V4 fluview `issues=`; Socrata `data.cdc.gov` resource and revisions path.
- Delphi docs: V5 API (`v5.html`), V5 queries (`v5_api_queries.html`), V4 to V5 migration guide (search summary, `v5_migration.html`), covidcast V4 page (search summary; 410 rule).
- CDC: NWSS data-methods (search summary); FluView overview (search summary); NREVSS pages (search summary).
- Papers (search summary): Schoen et al. 2023 (doi 10.1021/acs.est.3c07526); California EID 2026 (26-0306); Michigan/Ontario EID 2024 (24-0225); OFID 2025 (doi 10.1093/ofid/ofaf695.190); Lazer et al. 2014 (doi 10.1126/science.1248506); Yang, Santillana, Kou 2015 (doi 10.1073/pnas.1515373112); Santillana et al. 2015 (doi 10.1371/journal.pcbi.1004513); Shaman and Kohn 2009 (doi 10.1073/pnas.0806852106); Lancet 2013 England and Wales; Nature 2008 France; IJID 2024 (doi 10.1016/j.ijid.2024.01.005); Open-Meteo terms and pricing.

Unverified (3 maximum):

1. **[U] Ertem, Raymond, Meyers 2018, PLoS Comp Bio, doi 10.1371/journal.pcbi.1006236.** Not opened; no summary returned. Cited only as a pointer; no numbers used.
2. **[U] Google Health Trends end date.** Delphi pages conflict (2021 vs 2022-09). Conclusion (no 2025-26 series) does not depend on which is correct.
3. **[U] WastewaterSCAN payload and vintage.** Reachability checked (200), payload not inspected and no revision mechanism checked. Reason: time; treat as dated pulls only.

---

## 4. Failure modes

- **Look-ahead through revisions.** NHSN, NSSP, and NWSS revise (NWSS baselines recalculated Aug 1; winsorization changed Aug 2026). Mitigation: V5 `archive/` or `snapshot/` at fixed `snapshot_date`; store pull dates.
- **V4 retirement.** V4 covidcast queries after 2026-09-22 return 410 [D]. Mitigation: V5 only for new pulls; V4 only for historical reproduction, pre-cutoff.
- **Socrata has no visible revision history** [V]. Mitigation: dated pulls, versioned files.
- **Coarse resolution.** NSSP at 0.1 precision in some weeks. Mitigation: ignore differences below resolution.
- **Wastewater lead inconsistency** across sites and seasons (§2.4). Mitigation: per-site lead tests on dev seasons; no fixed lag.
- **Season-level overfitting.** Two dev seasons. Mitigation: shrinkage, permutation test, Track B shadow.
- **Clinical-lab selection bias** (§2.3). Mitigation: intensity-change use only.
- **Self-reported model-metadata.** Team claims are not evidence of benefit.
- **Licence constraints.** Open-Meteo non-commercial limits; CC-BY attribution.
- **Search data loss.** Google Health Trends unavailable; no feature depends on it.

---

## 5. Cost on a 4-CPU, 30-minute weekly budget

- V5 pulls (nssp, nhsn, fluview_ilinet, fluview_resp_lab_clinical, nwss): one call each with `snapshot/` or a bounded `archive/` `report_time_query`. Anonymous limits: 60 requests/hour, 5/min on `archive/`, 3/min on `snapshot/` [D]. Weekly total well under limits; use an API key if pulls grow. Seconds to a minute.
- Socrata and WastewaterSCAN pulls: a few MB per week; under 1 minute. Parse only in the monthly backtest.
- Weather: one archive fetch per location per season (53 locations), cached. Zero weekly cost after first pull.
- Event-stream aggregation: linear in events; under 10 seconds across 53 locations.
- Per-source fits: ridge or GBQR; multiply current fit time by K. Keep K ≤ 4 in Track B.
- Permutation test: 1,000 permutations over 2 seasons; under 1 minute on 4 CPUs.

Added weekly time: under 5 minutes [I].

---

## 6. Ranked experiments

Common rules: pre-registered before running; dev seasons 2023-24 and 2024-25, leave-one-season-out; vintage data only (V5 `snapshot/` at issue dates or `archive/` with `report_time_query`); pass requires a paired relWIS improvement over the current production model with permutation p < 0.1 across seasons. Track A may enter production after passing; Track B is shadow only.

1. **[Track A] NSSP and NHSN vintage audit.** Pull V5 `archive/` for nssp `pct_ed_visits_influenza` and nhsn `confirmed_admissions_flu_ew` for dev seasons; measure revision size by lag. Test: does using first-published values instead of latest change model 1 or 2 scores? Pass if not worse. This is a data-quality gate.
2. **[Track B] ILINet and NREVSS intensity features in GBQR.** Features: `fluview_ilinet` ili minus season-week mean; clinical percent_positive change over 2 weeks. Test: leave-one-season-out relWIS vs model 2 alone. Shadow one season before any promotion.
3. **[Track B] Wastewater lead by site.** Use V5 `nwss` (flu signals) with stored pulls; estimate per-site lead by cross-correlation with NHSN, dev seasons only. Pass if median lead ≥ 1 week with a 95% interval excluding zero and the feature improves h=2–3 scores. Shadow.
4. **[Track B] School-in-session indicator in EAKF.** Additive term; dev-season relWIS; calendar version recorded. Shadow.
5. **[Track B] Gated event-stream ensemble with shrinkage.** Up to 4 sources (NSSP, ILINet, NREVSS, wastewater); start at equal weights; shrinkage per §1.3; leave-one-season-out gate vs equal weights with permutation test. Shadow until two dev seasons pass; otherwise drop the gate and keep the best single-source model.

Dropped: Google Health Trends (unavailable). Subtype as a weekly feature (season covariate only).

---

## Top-5 recommendations

1. Pull all covidcast-type inputs from V5 (`snapshot/` with `snapshot_date`, `archive/` with `report_time_query`), not V4. V4 is frozen for 2026-27 and currently about 7 epiweeks behind fluview.
2. Run the NSSP and NHSN vintage audit first (experiment 1); it gates every other experiment.
3. Add ILINet and NREVSS intensity features to GBQR in shadow mode (experiment 2).
4. Use V5 `nwss` for wastewater with a per-site lead test (experiment 3). Socrata has no visible revision history, so keep dated pulls only.
5. Build the event-stream gate with α ≥ 0.5 shrinkage and a permutation test; promote only if it passes on both dev seasons.
