# Dev-season member forecasts

As-of forecasts of models 1 (EAKF) and 2 (GBQR) and their equal-weight linear pool
(MIX_LP) for every reference date of 2023-24 and 2024-25 (57 dates, 53 locations).
Admissions come from the hub version usable at each date (`run_vintage.pick_vintage`).
ED values are final for both models, because no ED vintages exist before Nov 2025.
Settings come from `model_config.json` and `model2_config.json`.

The per-date CSVs (`<ref>-CyberEpi-{EAKF,GBQR,MIX_LP}.csv`, about 52 MB) are gitignored.
Regenerate them with (Python 3.10+, lightgbm, about 3 min on 8 CPUs):

    python3 backtest/dev_members.py --ncpus 8

The hub data must be linked into `data/flusight/`, including `time-series.csv`.
`summary.json` holds relWIS vs FluSight-baseline per season.
`mix_lp_phase_error.csv` holds the MIX_LP median log error by as-of phase × horizon.
