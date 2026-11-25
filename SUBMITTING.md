# Submitting to CDC FluSight (owner checklist)

Everything is automated (`.github/workflows/weekly-forecast.yml`), including
the weekly pull request to the CDC hub once the token below is set. The owner
has given standing approval for weekly submissions in their name.

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

## Every week after (automatic)

The first submission (CyberEpi-EAKF, 2026-11-28) was merged by the hub
(cdcepi/FluSight-forecast-hub#4189). From then on the workflow opens each
week's pull request itself, from your fork, once this secret exists:

1. Create a classic token at https://github.com/settings/tokens/new with only
   the **public_repo** scope and an expiry after the season (2027-06-30).
2. In this repository: Settings → Secrets and variables → Actions → New
   repository secret, name `FLUSIGHT_PR_TOKEN`, paste the token.

Without the secret the step is skipped and the pull request is opened by
hand as before. The step never resubmits a file already in the hub and never
opens a second pull request for the same week. Model 2 (`CyberEpi-GBQR`) is
included from reference date 2026-12-05, with its metadata on first use.

## What the workflow guarantees

- Uses only data the CDC has published that week; refuses to forecast from
  last week's data (and fails loudly if data is still missing at the evening
  run, so a missed week is never silent).
- Frozen settings from `backtest/model_config.json`, chosen before any
  test-season result was seen.
- Validated against the hub's rules and official metadata schema.
