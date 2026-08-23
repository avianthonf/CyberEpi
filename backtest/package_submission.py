"""Package prospective forecast rows into FluSight hub-conformant layout.

Input: rows CSV from `run_flusight.py --reference-date R` (prospective mode).
Output:
  <out>/model-output/<team>-<model>/<R>-<team>-<model>.csv
  <out>/model-metadata/<team>-<model>.yml

Hub naming rules: team and model must be <15 chars, alphanumeric/underscore
only (no hyphens); the joined id uses a single hyphen.
"""
from __future__ import annotations

import argparse
import os
import re

import pandas as pd

COLUMNS = ["reference_date", "target", "horizon", "target_end_date",
           "location", "output_type", "output_type_id", "value"]

METHODS = ("SEIHDR mechanistic model, ensemble square-root filter "
           "assimilation, stochastic transmission and observation noise.")
METHODS_LONG = (
    "Age-aggregated SEIHDR compartmental influenza model per location; "
    "weekly incident admissions and NSSP ED ILI fraction assimilated with "
    "an ensemble square-root (EnSRF/EAKF) filter jointly estimating "
    "log-beta, log hospitalization ratio, and an ILI scaling factor as "
    "random-walk states; 300-member ensemble with multiplicative "
    "inflation; quantile forecasts from forward-integrated ensemble with "
    "per-day log-beta dispersion and multiplicative observation jitter; "
    "no spatial coupling — each location is filtered independently "
    "from its own observations."
)

METADATA_TEMPLATE = """team_name: {team_name}
team_abbr: {team}
model_name: {model_name}
model_abbr: {model}
model_contributors: [
  {{
    "name": "{name}",
    "affiliation": "{affiliation}",
    "email": "{email}"
  }}
]
license: cc-by-4.0
designated_model: true
data_inputs: "NHSN weekly confirmed influenza hospital admissions (target data); NSSP emergency department influenza visit fraction."
methods: "{methods}"
methods_long: "{methods_long}"
ensemble_of_models: false
ensemble_of_hub_models: false
website_url: {website}
repo_url: {repo}
"""


def valid_part(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]{1,14}", s))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows_csv", help="rows-<label>-<ref>.csv from prospective mode")
    ap.add_argument("--team", default="CyberEpi")
    ap.add_argument("--model", default="EAKF")
    ap.add_argument("--team-name", default="CyberEpi")
    ap.add_argument("--model-name", default="CyberEpi EAKF")
    ap.add_argument("--name", default=os.environ.get("GIT_AUTHOR_NAME", ""))
    ap.add_argument("--affiliation", default="CyberEpi Project")
    ap.add_argument("--email", default=os.environ.get("GIT_AUTHOR_EMAIL", ""))
    ap.add_argument("--website", default="https://github.com/avianthonf/CyberEpi")
    ap.add_argument("--repo", default="https://github.com/avianthonf/CyberEpi")
    ap.add_argument("--out", default="backtest/submission")
    args = ap.parse_args()

    if not (valid_part(args.team) and valid_part(args.model)):
        raise SystemExit("--team/--model must be 1-14 chars, [A-Za-z0-9_] only")
    model_id = f"{args.team}-{args.model}"

    df = pd.read_csv(args.rows_csv, dtype={"location": str, "output_type_id": str})
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise SystemExit(f"rows CSV missing columns: {missing}")
    refs = df["reference_date"].unique()
    if len(refs) != 1:
        raise SystemExit(f"expected exactly one reference_date, got {refs}")
    ref = refs[0]

    mo_dir = os.path.join(args.out, "model-output", model_id)
    meta_dir = os.path.join(args.out, "model-metadata")
    os.makedirs(mo_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    out_csv = os.path.join(mo_dir, f"{ref}-{model_id}.csv")
    df[COLUMNS].to_csv(out_csv, index=False)

    out_yml = os.path.join(meta_dir, f"{model_id}.yml")
    with open(out_yml, "w") as f:
        f.write(METADATA_TEMPLATE.format(
            team_name=args.team_name, team=args.team,
            model_name=args.model_name, model=args.model,
            name=args.name, affiliation=args.affiliation, email=args.email,
            methods=METHODS, methods_long=METHODS_LONG,
            website=args.website, repo=args.repo))

    print(f"wrote {out_csv} ({len(df)} rows) and {out_yml}")


if __name__ == "__main__":
    main()
