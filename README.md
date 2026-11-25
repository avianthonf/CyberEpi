# CyberEpi: flu hospitalization forecasting

CyberEpi forecasts weekly influenza hospital admissions for the US and 52
jurisdictions with a mechanistic SEIHDR model and an ensemble Kalman filter,
in the format of the CDC FluSight challenge. The goal is a forecasting record
scored by someone else: weekly live forecasts for the 2026-27 season, judged
against data that did not exist when they were made. See [ROADMAP.md](./ROADMAP.md).

## Results so far (honest backtest)

Forecasts made only from data as the CDC published it each week; settings
frozen after tuning on 2023-24; scored once on 2024-25 and 2025-26
(53 locations, horizons 0–3, 11,660 scores). Full detail:
[BACKTEST_RESULTS.md](./BACKTEST_RESULTS.md).

| Compared with | relWIS (below 1 = better) |
|---|---|
| CDC FluSight-baseline (persistence) | **0.697**, about 30% better |
| CDC FluSight-ensemble (all teams combined) | **1.046**, about level (3% better in 2024-25, 16% worse in 2025-26) |

Known weaknesses, stated up front:

- **Forecasts run low while epidemics decline.** The model's post-peak fall is
  too steep (3-week forecasts ~40% low in declining phases). An after-the-fact
  correction did not hold up on held-out seasons, so it is not applied; the
  fix belongs in the model ([backtest/calibrate.py](./backtest/calibrate.py)).
- **Intervals cover too little:** 90% intervals contain the truth ~74% of the time.
- **Still retrospective.** The live season is the real test.

An earlier headline (relWIS 0.714) used revised data and was tuned on the
seasons it reported; it is kept in [docs/archive/](./docs/archive/BACKTEST_RESULTS-2026-08.md)
with the reasons it was replaced.

## Live forecasting (2026-27)

`.github/workflows/weekly-forecast.yml` runs every Wednesday after the CDC
data release: it fetches the hub data, refuses to run on last week's data,
forecasts with the frozen settings in [backtest/model_config.json](./backtest/model_config.json),
validates the files against the hub's rules, and opens the pull request to the
CDC hub. Two models are submitted: CyberEpi-EAKF (designated) and, from
2026-12-05, CyberEpi-GBQR, a gradient-boosted quantile regression
([backtest/MODEL2_PROTOCOL.md](./backtest/MODEL2_PROTOCOL.md)). Details:
[SUBMITTING.md](./SUBMITTING.md).

```bash
pip install numpy pandas scipy jsonschema pyyaml lightgbm scikit-learn
git clone --depth 1 https://github.com/cdcepi/FluSight-forecast-hub hub
python3 backtest/live.py --hub hub --out forecasts
```

Reproducing the backtest takes about 45 minutes on 4 CPUs; commands are in
[BACKTEST_RESULTS.md](./BACKTEST_RESULTS.md#reproduce). Method details:
[backtest/METHODS.md](./backtest/METHODS.md).

Single-origin prospective mode: `python3 backtest/run_flusight.py
--reference-date YYYY-MM-DD` runs the filter through week R−7 and
forecasts a 4-week horizon exactly once — hub submission format via
`backtest/package_submission.py`, checked by `backtest/validate_submission.py`.

## History

CyberEpi began as a larger platform: a patient app, six backend services and
deployment configs around the forecasting model. It was removed on
2026-11-25 to keep the project to one claim that can be checked. The last
version with it is commit
[`509f9dc`](https://github.com/avianthonf/CyberEpi/tree/509f9dcbea82d4ccd9f2f8b3949c8508e584ce45).

## License & Citation

MIT — see [LICENSE](./LICENSE). If you use this software in research,
please cite it; see [CITATION.cff](./CITATION.cff).
