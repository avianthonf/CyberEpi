# Submitting to CDC FluSight (owner checklist)

Everything up to a valid forecast file is automated
(`.github/workflows/weekly-forecast.yml`). The steps below are public and in
your name, so they are yours to take (ROADMAP.md, checkpoint B).

## Decide

1. **Team and model abbreviation.** Default `CyberEpi-EAKF` (each part ≤ 14
   characters, letters, digits, underscore). Change with `--team` / `--model`
   in the workflow if you want something else. It cannot easily change later.
2. **Contributor details** shown publicly in the hub: name, affiliation, email.
3. **Public weekly record in this repo** (recommended): each forecast committed
   with a timestamp before scores exist, so anyone can check it was not edited
   after the fact.

## Set up (once)

In this repository: Settings → Secrets and variables → Actions → Variables:

| Variable | Value |
|---|---|
| `FORECAST_CONTRIBUTOR_NAME` | your name |
| `FORECAST_CONTRIBUTOR_EMAIL` | contact email (public in the hub) |
| `FORECAST_CONTRIBUTOR_AFFILIATION` | e.g. `Independent` |
| `COMMIT_FORECASTS` | `true` for the public weekly record |

Then fork `cdcepi/FluSight-forecast-hub` on GitHub.

## First submission

1. Actions → weekly-forecast → Run workflow (or wait for Wednesday).
2. Download the `forecast-<date>` artifact (or take it from `forecasts/`).
3. In your hub fork, add `model-metadata/CyberEpi-EAKF.yml` and
   `model-output/CyberEpi-EAKF/<date>-CyberEpi-EAKF.csv`, then open a pull
   request to `cdcepi/FluSight-forecast-hub` before **Wednesday 11pm ET**.
   The hub's own checks run on the pull request; fix anything they flag.

## Every week after

Copy that week's CSV into `model-output/CyberEpi-EAKF/` in your fork and open
a pull request by Wednesday 11pm ET. (Automating this pull request needs a
token with access to your fork; ask for it to be set up once the first
submission has gone through by hand.)

## What the workflow guarantees

- Uses only data the CDC has published that week; refuses to forecast from
  last week's data (and fails loudly if data is still missing at the evening
  run, so a missed week is never silent).
- Frozen settings from `backtest/model_config.json`, chosen before any
  test-season result was seen.
- Validated against the hub's rules and official metadata schema.
